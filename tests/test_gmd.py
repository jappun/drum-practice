from collections import Counter

import mido
import pytest

from drum_practice.gmd import (
    MIN_GENRE_BEATS,
    OTHER_GENRE,
    Performance,
    assign_difficulties,
    beat_id,
    build_beats,
    difficulty_features,
    genre_name,
    is_candidate,
    is_swung,
    merge_small_genres,
    pick_groove,
    read_onsets,
    segments,
    style_name,
)
from drum_practice.kit import DrumClass
from drum_practice.model import NORMAL, Note

TPB = 480  # ticks per quarter
SIXTEENTH = TPB // 4
K, S, HC = 36, 38, 42

# A 1-bar rock groove: hats on 8ths, kick on 1 and 3, snare on 2 and 4.
ROCK_BAR = [(s, HC) for s in range(0, 16, 2)] + [(0, K), (8, K), (4, S), (12, S)]
# A bar that's clearly different: a tom fill.
FILL_BAR = [(s, 48) for s in range(16)]


def write_midi(path, hits, push=0.0, velocity=90):
    """hits: (step, note) pairs; `push` shifts every hit by that many 16ths."""
    mid = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(100)))
    events = []
    for step, note in hits:
        tick = round((step + push) * SIXTEENTH)
        events += [(tick, "note_on", note, velocity), (tick + 30, "note_off", note, 0)]
    now = 0
    for tick, kind, note, vel in sorted(events, key=lambda e: (e[0], e[1] == "note_on")):
        track.append(mido.Message(kind, note=note, velocity=vel, channel=9, time=max(0, tick - now)))
        now = max(now, tick)
    mid.save(path)
    return path


def bars(*patterns):
    """Concatenate 1-bar patterns into one performance."""
    return [(i * 16 + s, n) for i, bar in enumerate(patterns) for s, n in bar]


# --- reading and quantising ---


def test_read_onsets_maps_notes_and_skips_unknown(tmp_path):
    path = write_midi(tmp_path / "a.mid", [(0, 36), (2, 44), (4, 26), (6, 99)])
    onsets = read_onsets(path)
    assert [o.drum for o in onsets] == [DrumClass.KICK, DrumClass.HH_PEDAL, DrumClass.HH_OPEN]
    assert [o.position for o in onsets] == [0, 2, 4]


def test_a_drummer_playing_consistently_early_still_lands_on_the_grid(tmp_path):
    path = write_midi(tmp_path / "a.mid", bars(ROCK_BAR, ROCK_BAR), push=-0.3)
    (seg,) = segments(read_onsets(path))
    assert {(n.step, n.drum) for n in seg.notes} >= {(0, DrumClass.KICK), (4, DrumClass.SNARE), (20, DrumClass.SNARE)}
    assert seg.ambiguous_share == 0


def test_same_drum_on_the_same_step_keeps_the_loudest(tmp_path):
    mid_path = tmp_path / "a.mid"
    write_midi(mid_path, bars(ROCK_BAR, ROCK_BAR) + [(4.2, S)], velocity=60)
    seg = segments(read_onsets(mid_path))[0]
    assert sum(1 for n in seg.notes if n.step == 4 and n.drum is DrumClass.SNARE) == 1


def test_windows_are_bar_aligned_and_two_bars_long(tmp_path):
    path = write_midi(tmp_path / "a.mid", bars(ROCK_BAR, ROCK_BAR, ROCK_BAR, ROCK_BAR))
    segs = segments(read_onsets(path))
    assert [s.start_step for s in segs] == [0, 16, 32]
    assert all(max(n.step for n in s.notes) < 32 for s in segs)


def test_velocities_are_relative_to_the_drummers_typical_hit(tmp_path):
    # A quiet player: typical hits at 60, one soft note at 30, one loud at 90.
    hits = [(s, HC) for s in range(0, 32, 2)] + [(4, S), (12, S), (20, S), (28, S)]
    path = write_midi(tmp_path / "a.mid", hits, velocity=60)
    mid = mido.MidiFile(path)
    for msg in mid.tracks[0]:
        if msg.type == "note_on" and msg.note == S:
            msg.velocity = 90  # snare accents
    mid.tracks[0].append(mido.Message("note_on", note=K, velocity=30, channel=9, time=0))
    mid.save(path)
    seg = segments(read_onsets(path))[0]
    by_drum = {n.drum: n.velocity for n in seg.notes}
    assert by_drum[DrumClass.HH_CLOSED] == NORMAL
    assert by_drum[DrumClass.SNARE] > NORMAL
    assert by_drum[DrumClass.KICK] < NORMAL


# --- choosing the groove ---


def test_pick_groove_skips_the_intro_and_fill(tmp_path):
    path = write_midi(tmp_path / "a.mid", bars(FILL_BAR, ROCK_BAR, ROCK_BAR, ROCK_BAR, ROCK_BAR, FILL_BAR))
    groove = pick_groove(segments(read_onsets(path)))
    assert groove is not None
    assert DrumClass.TOM_HIGH not in {n.drum for n in groove.notes}


def test_swung_offbeats_are_rejected(tmp_path):
    # Hats on swung 8ths: every off-beat lands 0.45 of a 16th late, between steps.
    swung_bar = [(s, HC) for s in range(0, 16, 4)] + [(s + 0.45, HC) for s in range(2, 16, 4)]
    swung_bar += [(0, K), (8, K), (4, S), (12, S)]
    path = write_midi(tmp_path / "a.mid", bars(swung_bar, swung_bar, swung_bar))
    segs = segments(read_onsets(path))
    assert segs and all(s.ambiguous_share > 0.15 for s in segs)
    assert pick_groove(segs) is None


def test_sparse_windows_are_not_picked(tmp_path):
    path = write_midi(tmp_path / "a.mid", [(0, K), (16, K), (31, K)])
    assert pick_groove(segments(read_onsets(path))) is None


# --- labels ---


@pytest.mark.parametrize(
    "style, genre, name",
    [
        ("dance/disco", "Dance", "Disco"),
        ("rock/groove4", "Rock", "Rock"),
        ("rock", "Rock", "Rock"),
        ("latin/brazilian-bossa", "Latin", "Bossa nova"),
        ("latin/brazilian-samba", "Latin", "Samba"),
        ("hiphop", "Hip-hop", "Hip-hop"),
        ("neworleans/secondline", "New Orleans", "Second line"),
        ("funk/fast", "Funk", "Funk"),
    ],
)
def test_genre_and_style_names(style, genre, name):
    assert genre_name(style) == genre
    assert style_name(style) == name


@pytest.mark.parametrize(
    "style, swung",
    [
        ("jazz", True),
        ("jazz/swing", True),
        ("jazz/fast", True),
        ("jazz/fusion", False),
        ("rock/shuffle", True),
        ("funk/purdieshuffle", True),
        ("blues/rock", True),
        ("rock", False),
        ("latin/brazilian-samba", False),
    ],
)
def test_swung_styles_are_excluded(style, swung):
    assert is_swung(style) is swung
    assert is_candidate(Performance("x.mid", style, 100, "beat", "4-4")) is (not swung)


def test_only_4_4_beats_are_candidates():
    assert not is_candidate(Performance("x.mid", "rock", 100, "fill", "4-4"))
    assert not is_candidate(Performance("x.mid", "rock", 100, "beat", "3-4"))


def test_small_genres_merge_into_other():
    merged = merge_small_genres({"Rock": 100, "Punk": MIN_GENRE_BEATS, "Gospel": MIN_GENRE_BEATS - 1})
    assert merged == {"Rock": "Rock", "Punk": "Punk", "Gospel": OTHER_GENRE}


def test_beat_ids_are_stable_and_filename_safe():
    p = Performance("drummer1/session2/14_rock-indie_94_beat_4-4.mid", "rock/indie", 94, "beat", "4-4")
    assert beat_id(p) == "gmd_drummer1_session2_14_rock_indie_94_beat_4_4"


# --- difficulty ---


def _features(notes_per_bar: int, tempo: float, offbeat: bool = False):
    step = 1 if offbeat else 2
    notes = tuple(Note(s, DrumClass.HH_CLOSED) for s in range(0, 32, step)[: notes_per_bar * 2])
    return difficulty_features(notes, tempo)


def test_difficulty_splits_into_even_thirds():
    feats = [_features(n % 8 + 4, 80 + n) for n in range(30)]
    assert Counter(assign_difficulties(feats)) == {"beginner": 10, "intermediate": 10, "advanced": 10}


def test_busier_faster_beats_rank_harder():
    easy = _features(4, 70)
    hard = _features(16, 160, offbeat=True)
    middle = _features(8, 110)
    assert assign_difficulties([hard, easy, middle]) == ["advanced", "beginner", "intermediate"]


# --- end to end on a tiny fake dataset ---


def test_build_beats_end_to_end_and_deterministic(tmp_path):
    files = {
        "d1/s1/1_rock_100_beat_4-4.mid": ("rock", "beat", "4-4"),
        "d1/s1/2_rock_100_beat_4-4.mid": ("rock/groove3", "beat", "4-4"),
        "d1/s1/3_dance-disco_100_beat_4-4.mid": ("dance/disco", "beat", "4-4"),
        "d1/s1/4_rock_100_fill_4-4.mid": ("rock", "fill", "4-4"),
        "d1/s1/5_jazz_100_beat_4-4.mid": ("jazz", "beat", "4-4"),
    }
    performances = []
    for name, (style, kind, sig) in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        write_midi(tmp_path / name, bars(ROCK_BAR, ROCK_BAR, ROCK_BAR))
        performances.append(Performance(name, style, 100, kind, sig))

    first = build_beats(performances, tmp_path)
    beats = [b for b, _ in first]
    assert [b.name for b in beats] == ["Rock 1", "Rock 2", "Disco 1"]
    assert {b.genre for b in beats} == {OTHER_GENRE}  # too few of each in this tiny set
    assert all(b.bars == 2 and b.tempo == 100 for b in beats)
    assert first[2][1]["style"] == "dance/disco"
    assert [(b.to_dict(), s) for b, s in build_beats(performances, tmp_path)] == [
        (b.to_dict(), s) for b, s in first
    ]
