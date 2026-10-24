import pytest

from drum_practice.kit import DrumClass
from drum_practice.model import ACCENT, GHOST, NORMAL, Beat, Note, load_beats


def _beat_dict(pattern: dict, bars: int = 1) -> dict:
    return {
        "name": "Test",
        "genre": "Rock",
        "difficulty": "beginner",
        "tempo": 90,
        "bars": bars,
        "pattern": pattern,
    }


def test_pattern_string_parses_steps_and_velocities():
    beat = Beat.from_dict(_beat_dict({"SNARE": "x-g- X--- .... ----", "KICK": "x--- ---- ---- ----"}))
    assert beat.notes == [
        Note(0, DrumClass.SNARE, NORMAL),
        Note(0, DrumClass.KICK, NORMAL),
        Note(2, DrumClass.SNARE, GHOST),
        Note(4, DrumClass.SNARE, ACCENT),
    ]


def test_notes_on_same_step_but_different_drums_are_distinct():
    assert Note(0, DrumClass.SNARE) != Note(0, DrumClass.KICK)


def test_wrong_length_pattern_is_rejected():
    with pytest.raises(ValueError, match="expected 16"):
        Beat.from_dict(_beat_dict({"SNARE": "x-x-"}))


def test_unknown_character_is_rejected():
    with pytest.raises(ValueError, match="unknown pattern character"):
        Beat.from_dict(_beat_dict({"SNARE": "x-?- ---- ---- ----"}))


def test_json_round_trip(tmp_path):
    beat = Beat.from_dict(
        _beat_dict(
            {
                "HH_OPEN": "---- ---- ---- --x- | ---- ---- ---- ----",
                "HH_CLOSED": "XxXx Xx-x XxXx XxXx | x-x- x-x- x-x- x-x-",
                "SNARE": "---- X--g -g-- X--g | ---- x--- ---- x---",
            },
            bars=2,
        )
    )
    path = tmp_path / "beat.json"
    beat.save(path)
    assert Beat.load(path) == beat


def test_step_timing():
    beat = Beat.from_dict(_beat_dict({"KICK": "x--- ---- ---- ---- | x--- ---- ---- ----"}, bars=2))
    assert beat.steps_per_bar == 16
    assert beat.total_steps == 32
    assert beat.step_seconds() == pytest.approx(60 / 90 / 4)


def test_beats_in_subfolders_load(tmp_path):
    (tmp_path / "set").mkdir()
    Beat.from_dict(_beat_dict({"KICK": "x--- ---- ---- ----"})).save(tmp_path / "set" / "one.json")
    beats = load_beats(tmp_path)
    assert [b.id for b in beats] == ["one"]
