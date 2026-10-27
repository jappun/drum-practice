"""Edit operations on beats for the beat editor. Pure: each returns a new Beat."""

from dataclasses import replace
from enum import Enum

from .kit import DrumClass
from .model import MAX_BEAT_BARS, Beat, Note


class Stroke(Enum):
    """What a click did, so a drag can keep doing the same thing."""

    ADD = "add"
    REMOVE = "remove"


def _without(beat: Beat, step: int, drum: DrumClass) -> list[Note]:
    return [n for n in beat.notes if not (n.step == step and n.drum is drum)]


def _with_notes(beat: Beat, notes: list[Note]) -> Beat:
    return replace(beat, notes=sorted(notes, key=Note.sort_key))


def note_at(beat: Beat, step: int, drum: DrumClass) -> Note | None:
    return next((n for n in beat.notes if n.step == step and n.drum is drum), None)


def click(beat: Beat, step: int, drum: DrumClass, velocity: int) -> tuple[Beat, Stroke]:
    """A click on a cell: empty → add a note at the brush velocity; a note at
    the brush velocity → remove it; a note at another velocity → change it to
    the brush. Returns the new beat and what a drag from here should do."""
    existing = note_at(beat, step, drum)
    if existing is not None and existing.velocity == velocity:
        return _with_notes(beat, _without(beat, step, drum)), Stroke.REMOVE
    return _with_notes(beat, _without(beat, step, drum) + [Note(step, drum, velocity)]), Stroke.ADD


def paint(beat: Beat, step: int, drum: DrumClass, stroke: Stroke, velocity: int) -> Beat:
    """A drag over a cell repeats the stroke the click started."""
    notes = _without(beat, step, drum)
    if stroke is Stroke.ADD:
        notes.append(Note(step, drum, velocity))
    return _with_notes(beat, notes)


def resize(beat: Beat, bars: int) -> Beat:
    """Change the beat's length: new bars start empty, removed bars lose
    their notes. (Practice's "Bars" setting repeats instead; this edits.)"""
    bars = max(1, min(MAX_BEAT_BARS, bars))
    total = bars * beat.steps_per_bar
    return replace(beat, bars=bars, notes=[n for n in beat.notes if n.step < total])


def blank(name: str = "New beat") -> Beat:
    return Beat(name=name, genre="Mine", difficulty="beginner", tempo=90.0, bars=2, notes=[])


def duplicate(beat: Beat) -> Beat:
    """An editable copy of a beat; it gets a fresh id when first saved."""
    return replace(beat, name=f"{beat.name} (copy)", notes=list(beat.notes), id="")


def same_music(a: Beat, b: Beat) -> bool:
    """Whether two beats would be played and graded the same (ignoring name,
    genre, level and tempo)."""
    return a.bars == b.bars and a.notes == b.notes

