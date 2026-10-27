import json
from fractions import Fraction as F

import pytest

from drum_practice.kit import DrumClass
from drum_practice.model import ACCENT, GHOST, NORMAL, Beat, Note, load_beats
from drum_practice.rhythm import TimeSignature

from conftest import FIXTURES

S, K, HC = DrumClass.SNARE, DrumClass.KICK, DrumClass.HH_CLOSED


def _format_1(pattern: dict, bars: int = 1) -> dict:
    return {"name": "Test", "genre": "Rock", "difficulty": "beginner", "tempo": 90, "bars": bars, "pattern": pattern}


def _beat(notes, ts="4/4", bars=1, **extra) -> Beat:
    return Beat(
        name="Test",
        genre="Rock",
        difficulty="beginner",
        tempo=90.0,
        bars=bars,
        notes=sorted(notes, key=Note.sort_key),
        time_signature=TimeSignature.parse(ts),
        **extra,
    )


# --- format 1 (pattern strings) still loads, converted to exact positions ---


def test_format_1_pattern_converts_to_positions_and_velocities():
    beat = Beat.from_dict(_format_1({"SNARE": "x-g- X--- .... ----", "KICK": "x--- ---- ---- ----"}))
    assert beat.notes == [
        Note(F(0), S, NORMAL),
        Note(F(0), K, NORMAL),
        Note(F(1, 2), S, GHOST),  # step 2 of 16ths = the "&" of beat 1
        Note(F(1), S, ACCENT),
    ]
    assert beat.time_signature == TimeSignature(4, 4) and beat.grid == 4


def test_format_1_is_saved_as_format_2_without_losing_anything(tmp_path):
    for fixture in FIXTURES.glob("*.json"):
        original = Beat.load(fixture)
        path = tmp_path / fixture.name
        original.save(path)
        data = json.loads(path.read_text())
        assert data["format"] == 2 and "pattern" not in data
        assert Beat.load(path) == original, fixture.name


def test_format_1_wrong_length_is_rejected():
    with pytest.raises(ValueError, match="expected 16"):
        Beat.from_dict(_format_1({"SNARE": "x-x-"}))


def test_format_1_unknown_character_is_rejected():
    with pytest.raises(ValueError, match="unknown pattern character"):
        Beat.from_dict(_format_1({"SNARE": "x-?- ---- ---- ----"}))


# --- format 2 ---


def test_notes_on_same_position_but_different_drums_are_distinct():
    assert Note(F(0), S) != Note(F(0), K)


def test_format_2_round_trip_with_triplets_32nds_and_odd_meters(tmp_path):
    beat = _beat(
        [
            Note(F(0), K, ACCENT),
            Note(F(1, 3), HC),
            Note(F(2, 3), HC, GHOST),
            Note(F(7, 8), S),  # a 32nd
            Note(F(5, 2), S, NORMAL, length=F(1, 2)),
        ],
        ts="7/8",
        bars=2,
        grid=2,
        divisions={0: 6},
    )
    path = tmp_path / "beat.json"
    beat.save(path)
    assert Beat.load(path) == beat


def test_format_2_is_readable():
    beat = _beat([Note(F(5, 3), S), Note(F(0), K, ACCENT)])
    data = beat.to_dict()
    assert data["notes"] == [
        {"at": "0", "drum": "KICK", "v": "X"},
        {"at": "1+2/3", "drum": "SNARE", "v": "x"},
    ]
    assert data["time_signature"] == "4/4" and data["grid"] == "16ths"


def test_named_divisions_are_stored_by_name():
    data = _beat([], divisions={3: 3}).to_dict()
    assert data["divisions"] == {"3": "8th triplets"}


def test_note_outside_the_beat_is_rejected():
    data = _beat([]).to_dict()
    data["notes"] = [{"at": "4", "drum": "KICK", "v": "x"}]  # one 4/4 bar ends at 4
    with pytest.raises(ValueError, match="outside the beat"):
        Beat.from_dict(data)


def test_bad_velocity_mark_is_rejected():
    data = _beat([]).to_dict()
    data["notes"] = [{"at": "0", "drum": "KICK", "v": "?"}]
    with pytest.raises(ValueError, match="velocity mark"):
        Beat.from_dict(data)


# --- lengths and grid ---


@pytest.mark.parametrize(
    "ts, bar, beat, beats",
    [("4/4", 4, 1, 4), ("3/4", 3, 1, 3), ("6/8", 3, F(3, 2), 2), ("7/8", F(7, 2), F(1, 2), 7), ("2/2", 4, 2, 2)],
)
def test_lengths_follow_the_time_signature(ts, bar, beat, beats):
    b = _beat([], ts=ts, bars=2)
    assert b.bar_quarters == bar and b.beat_quarters == beat and b.beats_per_bar == beats
    assert b.total_quarters == 2 * bar and b.total_beats == 2 * beats


def test_seconds_use_quarter_note_tempo():
    b = _beat([])
    assert b.seconds(1) == pytest.approx(60 / 90)
    assert b.duration_seconds == pytest.approx(4 * 60 / 90)


def test_grid_shows_the_finest_division_needed_per_beat():
    b = _beat([Note(F(1, 4), HC), Note(F(1) + F(1, 3), HC), Note(F(2) + F(1, 8), S)], grid=4)
    assert b.columns_in_beat(0) == 4  # 16ths fit
    assert b.columns_in_beat(1) == 12  # a triplet in a 16th beat needs 12 columns
    assert b.columns_in_beat(2) == 8  # a 32nd
    assert b.columns_in_beat(3) == 4  # empty: the default


def test_a_beat_divided_into_triplets_needs_no_more_columns():
    b = _beat([Note(F(1, 3), HC), Note(F(2, 3), HC)], divisions={0: 3})
    assert b.columns_in_beat(0) == 3


def test_beats_in_subfolders_load(tmp_path):
    (tmp_path / "set").mkdir()
    _beat([Note(F(0), K)]).save(tmp_path / "set" / "one.json")
    assert [b.id for b in load_beats(tmp_path)] == ["one"]
