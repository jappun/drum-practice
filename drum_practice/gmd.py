"""Turning Groove MIDI Dataset performances into library beats.

Pure functions over note lists, so they can be tested without the dataset.
`scripts/import_gmd.py` does the downloading and file writing.

The Groove MIDI Dataset is by Google LLC, licensed CC BY 4.0:
Gillick, Roberts, Engel, Eck and Bamman, "Learning to Groove with Inverse
Sequence Transformations", ICML 2019.
"""

import re
import statistics
from dataclasses import dataclass
from pathlib import Path

import mido

from .kit import DrumClass, classify
from .library import DIFFICULTIES, OTHER_GENRE
from .model import NORMAL, Beat, Note

STEPS_PER_BEAT = 4
STEPS_PER_BAR = 16
SEGMENT_BARS = 2
SEGMENT_STEPS = SEGMENT_BARS * STEPS_PER_BAR
MIN_SEGMENT_NOTES = 16
# A note further than this from any 16th (after removing the drummer's
# overall push/pull) is "between" two steps, as in swung or triplet feels.
AMBIGUOUS_OFFSET = 0.35
MAX_AMBIGUOUS_SHARE = 0.15
MIN_GENRE_BEATS = 5  # genres with fewer usable beats are filed under OTHER_GENRE

GENRE_NAMES = {
    "afrobeat": "Afrobeat",
    "afrocuban": "Afro-Cuban",
    "blues": "Blues",
    "country": "Country",
    "dance": "Dance",
    "funk": "Funk",
    "gospel": "Gospel",
    "highlife": "Highlife",
    "hiphop": "Hip-hop",
    "jazz": "Jazz",
    "latin": "Latin",
    "middleeastern": "Middle Eastern",
    "neworleans": "New Orleans",
    "pop": "Pop",
    "punk": "Punk",
    "reggae": "Reggae",
    "rock": "Rock",
    "soul": "Soul",
}

# Secondary style labels that are session notes rather than styles.
_NOT_A_STYLE = re.compile(r"^(groove\d+|fast|slow|mediumfast|soft)$")
_STYLE_NAMES = {
    "brazilian": "Brazilian",
    "brazilian-bossa": "Bossa nova",
    "brazilian-sambareggae": "Samba-reggae",
    "chacha": "Cha-cha",
    "dominican-merengue": "Merengue",
    "halftime": "Half-time",
    "hiphop": "Hip-hop",
    "purdieshuffle": "Purdie shuffle",
    "secondline": "Second line",
}


@dataclass(frozen=True)
class Onset:
    position: float  # in 16th steps from the start of the file
    drum: DrumClass
    velocity: int


def read_onsets(path: Path) -> list[Onset]:
    """Every mapped drum hit in a MIDI file, positioned in 16th steps."""
    mid = mido.MidiFile(path)
    sixteenth = mid.ticks_per_beat / STEPS_PER_BEAT
    ticks = 0
    onsets = []
    for msg in mido.merge_tracks(mid.tracks):
        ticks += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            drum = classify(msg.note)
            if drum is not None:
                onsets.append(Onset(ticks / sixteenth, drum, msg.velocity))
    return onsets


def _signed_offset(position: float) -> float:
    """Distance from the nearest 16th, in steps, in [-0.5, 0.5)."""
    return (position + 0.5) % 1 - 0.5


def feel_shift(onsets: list[Onset]) -> float:
    """How far ahead (negative) or behind the drummer sits overall, measured
    on notes near the beat. Off-beat notes are left out so a swung feel
    can't drag the estimate halfway and disguise itself as straight."""
    on_beat = [o.position for o in onsets if round(o.position) % STEPS_PER_BEAT == 0]
    positions = on_beat if len(on_beat) >= 4 else [o.position for o in onsets]
    return statistics.median(_signed_offset(p) for p in positions)


@dataclass(frozen=True)
class Segment:
    start_step: int  # bar-aligned, within the whole performance
    notes: tuple[Note, ...]  # steps relative to the segment start
    ambiguous_share: float


def segments(onsets: list[Onset]) -> list[Segment]:
    """Every bar-aligned 2-bar window, quantised after removing the drummer's
    overall shift. Velocities are scaled so the performance's typical hit is
    NORMAL, making ghosts and accents relative to how that drummer played.
    Same drum on the same step keeps the loudest hit."""
    if not onsets:
        return []
    shift = feel_shift(onsets)
    scale = NORMAL / statistics.median(o.velocity for o in onsets)
    placed = []  # (step, drum, velocity, ambiguous)
    for o in onsets:
        pos = o.position - shift
        step = round(pos)
        velocity = max(1, min(127, round(o.velocity * scale)))
        placed.append((step, o.drum, velocity, abs(pos - step) > AMBIGUOUS_OFFSET))

    whole_bars = max(p[0] for p in placed) // STEPS_PER_BAR + 1
    out = []
    for start in range(0, (whole_bars - SEGMENT_BARS) * STEPS_PER_BAR + 1, STEPS_PER_BAR):
        inside = [p for p in placed if start <= p[0] < start + SEGMENT_STEPS]
        if not inside:
            continue
        loudest: dict[tuple[int, DrumClass], int] = {}
        for step, drum, velocity, _ in inside:
            key = (step - start, drum)
            loudest[key] = max(loudest.get(key, 0), velocity)
        notes = tuple(sorted((Note(s, d, v) for (s, d), v in loudest.items()), key=Note.sort_key))
        ambiguous = sum(p[3] for p in inside) / len(inside)
        out.append(Segment(start, notes, ambiguous))
    return out


def _signature(segment: Segment) -> frozenset[tuple[int, DrumClass]]:
    return frozenset((n.step, n.drum) for n in segment.notes)


def pick_groove(candidates: list[Segment]) -> Segment | None:
    """The window most like all the others: the performance's main groove,
    rather than an intro, fill or ending. None if no window is usable."""
    usable = [
        s
        for s in candidates
        if s.ambiguous_share <= MAX_AMBIGUOUS_SHARE and len(s.notes) >= MIN_SEGMENT_NOTES
    ]
    if not usable:
        return None
    sigs = [_signature(s) for s in usable]

    def typicality(i: int) -> float:
        a = sigs[i]
        return sum(len(a & b) / len(a | b) for j, b in enumerate(sigs) if j != i)

    # Ties go to the earliest window, so the choice is deterministic.
    best = max(range(len(usable)), key=lambda i: (typicality(i), -usable[i].start_step))
    return usable[best]


# --- naming and genres ---


def genre_name(style: str) -> str:
    primary = style.split("/")[0]
    return GENRE_NAMES.get(primary, primary.title())


def style_name(style: str) -> str:
    """The most specific readable style: the secondary label if it's a real
    style (e.g. "dance/disco" -> "Disco"), else the genre."""
    primary, _, secondary = style.partition("/")
    if not secondary or _NOT_A_STYLE.match(secondary):
        return genre_name(style)
    if secondary in _STYLE_NAMES:
        return _STYLE_NAMES[secondary]
    for prefix in ("brazilian-", "venezuelan-", "dominican-"):
        secondary = secondary.removeprefix(prefix)
    return secondary.replace("-", " ").capitalize()


def merge_small_genres(genre_counts: dict[str, int]) -> dict[str, str]:
    """Display genre for each genre: itself, or OTHER_GENRE if too small."""
    return {g: (g if n >= MIN_GENRE_BEATS else OTHER_GENRE) for g, n in genre_counts.items()}


# --- difficulty ---

# Weights for each feature's percentile rank across the imported set.
DIFFICULTY_WEIGHTS = {"density": 0.35, "syncopation": 0.30, "tempo": 0.20, "variety": 0.15}


def difficulty_features(notes: tuple[Note, ...], tempo: float) -> dict[str, float]:
    return {
        "density": len(notes) / SEGMENT_BARS,
        # Notes on the "e" and "a" of each beat (odd 16ths) are the syncopated ones.
        "syncopation": sum(n.step % 2 for n in notes) / len(notes),
        "tempo": tempo,
        "variety": len({n.drum for n in notes}),
    }


def assign_difficulties(features: list[dict[str, float]]) -> list[str]:
    """Rank every beat by a weighted blend of percentile ranks, then split
    the set into equal thirds: beginner, intermediate, advanced."""
    n = len(features)
    if n == 0:
        return []

    def percentile_ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        for rank, i in enumerate(order):
            ranks[i] = rank / max(1, n - 1)
        return ranks

    scores = [0.0] * n
    for name, weight in DIFFICULTY_WEIGHTS.items():
        for i, r in enumerate(percentile_ranks([f[name] for f in features])):
            scores[i] += weight * r

    order = sorted(range(n), key=lambda i: scores[i])
    levels = [""] * n
    for position, i in enumerate(order):
        levels[i] = DIFFICULTIES[min(len(DIFFICULTIES) - 1, position * len(DIFFICULTIES) // n)]
    return levels


# --- putting it together ---


@dataclass(frozen=True)
class Performance:
    """One row of the dataset's info.csv that we care about."""

    midi_filename: str
    style: str
    bpm: int
    beat_type: str
    time_signature: str


# Swung feels can't be written on a straight 16th grid: swung 8ths land
# between steps and get snapped to the wrong one. The timing check in
# `segments` misses light or exact-triplet swing, so these are excluded by
# their labels. Jazz is swung unless its sub-style says otherwise.
SWUNG_SUBSTYLES = {"swing", "shuffle", "purdieshuffle"}
SWUNG_GENRES = {"blues"}
STRAIGHT_JAZZ_SUBSTYLES = {"fusion", "funk", "linear", "march", "klezmer"}


def is_swung(style: str) -> bool:
    primary, _, secondary = style.partition("/")
    if secondary in SWUNG_SUBSTYLES or primary in SWUNG_GENRES:
        return True
    return primary == "jazz" and secondary not in STRAIGHT_JAZZ_SUBSTYLES


def is_candidate(p: Performance) -> bool:
    return p.beat_type == "beat" and p.time_signature == "4-4" and not is_swung(p.style)


def beat_id(p: Performance) -> str:
    stem = p.midi_filename.removesuffix(".mid")
    return "gmd_" + re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower()


def build_beats(performances: list[Performance], root: Path) -> list[tuple[Beat, dict]]:
    """Library beats (with their source info) from the dataset at `root`."""
    chosen = []  # (performance, segment)
    for p in sorted(performances, key=lambda p: p.midi_filename):
        if not is_candidate(p):
            continue
        groove = pick_groove(segments(read_onsets(root / p.midi_filename)))
        if groove is not None:
            chosen.append((p, groove))

    counts: dict[str, int] = {}
    for p, _ in chosen:
        counts[genre_name(p.style)] = counts.get(genre_name(p.style), 0) + 1
    display_genre = merge_small_genres(counts)
    levels = assign_difficulties([difficulty_features(seg.notes, p.bpm) for p, seg in chosen])

    numbering: dict[str, int] = {}
    out = []
    for (p, seg), level in zip(chosen, levels):
        style = style_name(p.style)
        numbering[style] = numbering.get(style, 0) + 1
        beat = Beat(
            name=f"{style} {numbering[style]}",
            genre=display_genre[genre_name(p.style)],
            difficulty=level,
            tempo=float(p.bpm),
            bars=SEGMENT_BARS,
            notes=list(seg.notes),
            id=beat_id(p),
        )
        source = {
            "dataset": "Groove MIDI Dataset (CC BY 4.0)",
            "file": p.midi_filename,
            "style": p.style,
            "bars": f"{seg.start_step // STEPS_PER_BAR + 1}-{seg.start_step // STEPS_PER_BAR + SEGMENT_BARS}",
        }
        out.append((beat, source))
    return out
