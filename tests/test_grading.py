import pytest

from drum_practice.grading import (
    EXTRA_PENALTY,
    GOOD_CREDIT,
    Expected,
    Played,
    Verdict,
    grade,
)
from drum_practice.kit import DrumClass

K, S = DrumClass.KICK, DrumClass.SNARE
HC, HO, HP = DrumClass.HH_CLOSED, DrumClass.HH_OPEN, DrumClass.HH_PEDAL


def exp(*notes):
    return [Expected(t, d, step) for step, (t, d) in enumerate(notes)]


def hits(*notes):
    return [Played(t, d) for t, d in notes]


BASIC = exp((0.0, K), (0.5, S), (1.0, K), (1.5, S))


def test_perfect_performance_scores_100():
    result = grade(BASIC, hits((0.0, K), (0.5, S), (1.0, K), (1.5, S)))
    assert result.count(Verdict.PERFECT) == 4
    assert result.extras == []
    assert result.score == 100


def test_uniform_shift_is_graded_by_window():
    good = grade(BASIC, hits((0.05, K), (0.55, S), (1.05, K), (1.55, S)))
    assert good.count(Verdict.GOOD) == 4
    assert good.score == pytest.approx(GOOD_CREDIT * 100)
    assert good.mean_offset == pytest.approx(0.05)

    too_late = grade(BASIC, hits((0.1, K), (0.6, S), (1.1, K), (1.6, S)))
    assert too_late.count(Verdict.MISS) == 4
    assert len(too_late.extras) == 4
    assert too_late.score == 0


def test_early_and_late_offsets_have_signs():
    result = grade(exp((1.0, S)), hits((0.96, S)))
    assert result.notes[0].verdict is Verdict.GOOD
    assert result.notes[0].early
    assert result.notes[0].offset == pytest.approx(-0.04)


def test_missing_notes():
    result = grade(BASIC, hits((0.0, K), (1.0, K)))
    assert result.count(Verdict.PERFECT) == 2
    assert result.count(Verdict.MISS) == 2
    assert result.score == 50


def test_wrong_drum_is_a_miss_plus_an_extra():
    result = grade(exp((0.5, S)), hits((0.5, K)))
    assert result.notes[0].verdict is Verdict.MISS
    assert result.extras == hits((0.5, K))


def test_extras_cost_points():
    result = grade(BASIC, hits((0.0, K), (0.5, S), (1.0, K), (1.5, S), (0.25, S)))
    assert len(result.extras) == 1
    assert result.score == pytest.approx((4 - EXTRA_PENALTY) / 4 * 100)


def test_double_hit_matches_the_closer_one_and_the_other_is_extra():
    result = grade(exp((0.5, S)), hits((0.48, S), (0.51, S)))
    assert result.notes[0].offset == pytest.approx(0.01)
    assert result.extras == hits((0.48, S))


def test_tightest_pairs_win_so_a_stray_cannot_steal_a_note():
    # The hit at 0.62 is in reach of both notes. Matching in order would give
    # it to 0.5 and leave 0.62 without its exact hit; tightest-first doesn't.
    result = grade(exp((0.5, S), (0.62, S)), hits((0.56, S), (0.62, S)))
    assert [n.verdict for n in result.notes] == [Verdict.GOOD, Verdict.PERFECT]
    assert result.extras == []


def test_empty_beat_with_no_hits_scores_100():
    assert grade([], []).score == 100


# --- Hi-hat pedal second pass ---


def test_pedal_chick_with_a_closed_hit_is_ignored():
    result = grade(exp((1.0, HC)), hits((1.0, HC), (1.02, HP)))
    assert result.extras == []
    assert result.ignored == hits((1.02, HP))


def test_pedal_chick_closing_an_open_hat_is_ignored():
    result = grade(exp((0.5, HO)), hits((0.5, HO), (0.75, HP)))
    assert result.extras == []
    assert result.ignored == hits((0.75, HP))


def test_second_chick_after_one_open_hit_is_an_extra():
    result = grade(exp((0.5, HO)), hits((0.5, HO), (0.75, HP), (1.0, HP)))
    assert result.ignored == hits((0.75, HP))
    assert result.extras == hits((1.0, HP))


def test_chick_within_40ms_after_an_open_hit_is_a_choke_and_an_extra():
    result = grade(exp((0.5, HO)), hits((0.5, HO), (0.52, HP)))
    assert result.extras == hits((0.52, HP))


def test_lone_chick_is_an_extra():
    result = grade(exp((0.5, S)), hits((0.5, S), (1.0, HP)))
    assert result.extras == hits((1.0, HP))


def test_chick_after_a_closed_hit_is_an_extra():
    result = grade(exp((0.5, HC)), hits((0.5, HC), (0.75, HP)))
    assert result.extras == hits((0.75, HP))


def test_written_pedal_note_is_graded_normally_even_beside_a_hihat_hit():
    result = grade(exp((1.0, HC), (1.0, HP)), hits((1.0, HC), (1.01, HP)))
    assert [n.verdict for n in result.notes] == [Verdict.PERFECT, Verdict.PERFECT]
    assert result.ignored == []


def test_chick_with_a_missed_closed_hit_after_an_open_counts_as_the_close():
    # Open on "&4", stick hit on "1" missed, but the foot closed the hat there.
    result = grade(exp((0.5, HO), (0.75, HC)), hits((0.5, HO), (0.75, HP)))
    assert result.notes[1].verdict is Verdict.MISS
    assert result.extras == []
    assert result.ignored == hits((0.75, HP))
