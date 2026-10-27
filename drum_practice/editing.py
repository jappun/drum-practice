"""Edit operations on beats for the beat editor. Pure: each returns a new Beat."""

from dataclasses import replace
from enum import Enum
from fractions import Fraction

from .kit import DrumClass
from .model import MAX_BEAT_BARS, Beat, Note, default_grid
from .rhythm import TimeSignature


class Stroke(Enum):
    """What a click did, so a drag can keep doing the same thing."""

    ADD = "add"
    REMOVE = "remove"


def _without(beat: Beat, at: Fraction, drum: DrumClass) -> list[Note]:
    return [n for n in beat.notes if not (n.at == at and n.drum is drum)]


def _with_notes(beat: Beat, notes: list[Note]) -> Beat:
    return replace(beat, notes=sorted(notes, key=Note.sort_key))


def note_at(beat: Beat, at: Fraction, drum: DrumClass) -> Note | None:
    return next((n for n in beat.notes if n.at == at and n.drum is drum), None)


def click(beat: Beat, at: Fraction, drum: DrumClass, velocity: int) -> tuple[Beat, Stroke]:
    """A click on a cell: empty → add a note at the brush velocity; a note at
    the brush velocity → remove it; a note at another velocity → change it to
    the brush. Returns the new beat and what a drag from here should do."""
    existing = note_at(beat, at, drum)
    if existing is not None and existing.velocity == velocity:
        return _with_notes(beat, _without(beat, at, drum)), Stroke.REMOVE
    return _with_notes(beat, _without(beat, at, drum) + [Note(at, drum, velocity)]), Stroke.ADD


def paint(beat: Beat, at: Fraction, drum: DrumClass, stroke: Stroke, velocity: int) -> Beat:
    """A drag over a cell repeats the stroke the click started."""
    notes = _without(beat, at, drum)
    if stroke is Stroke.ADD:
        notes.append(Note(at, drum, velocity))
    return _with_notes(beat, notes)


def resize(beat: Beat, bars: int) -> Beat:
    """Change the beat's length: new bars start empty, removed bars lose
    their notes. (Practice's "Bars" setting repeats instead; this edits.)"""
    bars = max(1, min(MAX_BEAT_BARS, bars))
    end = bars * beat.bar_quarters
    total_beats = bars * beat.beats_per_bar
    return replace(
        beat,
        bars=bars,
        notes=[n for n in beat.notes if n.at < end],
        divisions={i: c for i, c in beat.divisions.items() if i < total_beats},
    )


# --- subdivisions and time signature ---


def _snap(beat: Beat, notes: list[Note], columns_for) -> tuple[list[Note], int]:
    """Move each note to the nearest column of its beat (`columns_for(beat
    index)` columns), keeping the loudest if two land together. Returns the
    notes and how many moved."""
    placed: dict[tuple[Fraction, DrumClass], Note] = {}
    moved = 0
    for n in notes:
        i = beat.beat_index(n.at)
        start = i * beat.beat_quarters
        col = beat.beat_quarters / columns_for(i)
        snapped = start + round((n.at - start) / col) * col
        if snapped >= beat.total_quarters:
            snapped -= col  # don't push the last note past the end
        moved += snapped != n.at
        key = (snapped, n.drum)
        if key not in placed or n.velocity > placed[key].velocity:
            placed[key] = replace(n, at=snapped)
    return sorted(placed.values(), key=Note.sort_key), moved


def set_grid(beat: Beat, columns: int) -> tuple[Beat, int]:
    """Use `columns` per beat everywhere (clearing per-beat choices). Notes
    that fall between the new columns move to the nearest one; returns the
    new beat and how many notes moved."""
    shaped = replace(beat, grid=columns, divisions={})
    notes, moved = _snap(shaped, beat.notes, lambda i: columns)
    return replace(shaped, notes=notes), moved


def set_beat_columns(beat: Beat, index: int, columns: int) -> tuple[Beat, int]:
    """Use `columns` for one beat only; its notes snap like `set_grid`."""
    divisions = dict(beat.divisions)
    if columns == beat.grid:
        divisions.pop(index, None)
    else:
        divisions[index] = columns
    shaped = replace(beat, divisions=divisions)
    inside = [n for n in beat.notes if beat.beat_index(n.at) == index]
    others = [n for n in beat.notes if beat.beat_index(n.at) != index]
    snapped, moved = _snap(shaped, inside, lambda i: columns)
    return replace(shaped, notes=sorted(others + snapped, key=Note.sort_key)), moved


def set_time_signature(beat: Beat, ts: TimeSignature) -> tuple[Beat, int]:
    """Change the meter. Bars keep their count, notes past the new end are
    dropped, and the grid goes back to 16ths in the new meter, with notes
    snapped onto it like `set_grid`. Returns the beat and how many moved."""
    shaped = replace(beat, time_signature=ts, grid=default_grid(ts), divisions={})
    kept = [n for n in beat.notes if n.at < shaped.total_quarters]
    notes, moved = _snap(shaped, kept, lambda i: shaped.grid)
    return replace(shaped, notes=notes), moved


def blank(name: str = "New beat") -> Beat:
    return Beat(name=name, genre="Mine", difficulty="beginner", tempo=90.0, bars=2, notes=[])


def duplicate(beat: Beat) -> Beat:
    """An editable copy of a beat; it gets a fresh id when first saved."""
    return replace(
        beat, name=f"{beat.name} (copy)", notes=list(beat.notes), divisions=dict(beat.divisions), id=""
    )


def same_music(a: Beat, b: Beat) -> bool:
    """Whether two beats would be played and graded the same (ignoring name,
    genre, level, tempo and how the grid is divided)."""
    return a.bars == b.bars and a.time_signature == b.time_signature and a.notes == b.notes
