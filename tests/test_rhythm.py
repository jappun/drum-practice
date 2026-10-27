from fractions import Fraction as F

import pytest

from drum_practice.rhythm import (
    SUBDIVISIONS,
    TimeSignature,
    columns_to_fit,
    format_position,
    parse_position,
    subdivision_for,
    subdivision_named,
)


@pytest.mark.parametrize(
    "text, value",
    [("0", F(0)), ("2", F(2)), ("3/4", F(3, 4)), ("1+2/3", F(5, 3)), (" 3 + 1/8 ", F(25, 8)), ("6/4", F(3, 2))],
)
def test_parse_position(text, value):
    assert parse_position(text) == value


@pytest.mark.parametrize("value", [F(0), F(3), F(1, 3), F(5, 3), F(7, 8), F(25, 8), F(1, 12)])
def test_format_then_parse_is_exact(value):
    assert parse_position(format_position(value)) == value


def test_format_uses_the_shortest_form():
    assert format_position(F(2)) == "2"
    assert format_position(F(3, 4)) == "3/4"
    assert format_position(F(5, 3)) == "1+2/3"


@pytest.mark.parametrize("bad", ["", "x", "1/0", "1+2", "-1", "1.5"])
def test_bad_positions_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_position(bad)


def test_triplets_add_up_exactly():
    third = parse_position("1/3")
    assert third + third + third == 1  # no floating-point drift


def test_time_signatures():
    assert str(TimeSignature.parse("6/8")) == "6/8"
    assert TimeSignature(6, 8).compound and not TimeSignature(3, 8).compound
    assert TimeSignature(12, 8).beats_per_bar == 4
    with pytest.raises(ValueError):
        TimeSignature(4, 5)


def test_subdivisions_only_fit_where_they_divide_a_beat_evenly():
    four_four, six_eight = TimeSignature(4, 4), TimeSignature(6, 8)
    assert [s.columns(four_four) for s in SUBDIVISIONS] == [4, 3, 6, 8]
    assert subdivision_named("8th triplets").columns(six_eight) is None  # 4.5 per dotted quarter
    assert subdivision_named("16ths").columns(six_eight) == 6
    assert subdivision_for(3, four_four).name == "8th triplets"
    assert subdivision_for(5, four_four) is None


def test_columns_to_fit_picks_the_finest_grid_needed():
    beat = F(1)
    assert columns_to_fit([], beat, at_least=4) == 4
    assert columns_to_fit([F(1, 4), F(1, 2)], beat, at_least=4) == 4
    assert columns_to_fit([F(1, 3)], beat, at_least=4) == 12
    assert columns_to_fit([F(1, 3)], beat, at_least=3) == 3
    assert columns_to_fit([F(1, 8)], beat, at_least=4) == 8
    assert columns_to_fit([F(1, 2)], F(3, 2), at_least=1) == 3  # 6/8: an 8th in a dotted-quarter beat
