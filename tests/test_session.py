import numpy as np
import pytest

from drum_practice.audio import Mixer
from drum_practice.calibration import MAX_SCATTER, MEASURED_CLICKS, measure
from drum_practice.model import Beat
from drum_practice.session import Stage, Timeline
from drum_practice.settings import Settings
from drum_practice.sounds import build_clicks, build_kit

from conftest import FIXTURES

SR = 48_000


@pytest.fixture
def beat():
    return Beat.load(FIXTURES / "basic_rock.json")  # 2 bars at 90 BPM


def test_sequence_is_count_in_demo_count_in_play(beat):
    tl = Timeline(beat, start=1_000, sample_rate=SR)
    assert [s.stage for s in tl.segments] == [Stage.COUNT_IN, Stage.DEMO, Stage.COUNT_IN, Stage.PLAY]

    bar = beat.seconds(beat.bar_quarters) * SR
    lengths_in_bars = [round((s.end - s.start) / bar, 6) for s in tl.segments]
    assert lengths_in_bars == [1, 2, 1, 2]
    for a, b in zip(tl.segments, tl.segments[1:]):
        assert a.end == b.start
    assert tl.segments[0].start == 1_000


def test_without_count_in_demo_runs_straight_into_play(beat):
    tl = Timeline(beat, start=0, sample_rate=SR, count_in=False)
    assert [s.stage for s in tl.segments] == [Stage.DEMO, Stage.PLAY]


def test_stage_at_reports_stage_and_position(beat):
    tl = Timeline(beat, start=0, sample_rate=SR)
    quarter = beat.seconds(1) * SR
    assert tl.stage_at(0) == (Stage.COUNT_IN, 0)
    stage, position = tl.stage_at(tl.segment(Stage.DEMO).start + 1.375 * quarter)
    assert stage is Stage.DEMO and position == pytest.approx(1.375)
    assert tl.stage_at(tl.segment(Stage.PLAY).start)[0] is Stage.PLAY
    assert tl.stage_at(tl.end)[0] is Stage.DONE


def test_clicks_fall_on_each_count_in_beat_with_accent_on_one(beat):
    tl = Timeline(beat, start=0, sample_rate=SR)
    clicks = tl.clicks()
    assert len(clicks) == 2 * beat.beats_per_bar
    beat_samples = 60 / beat.tempo * SR
    assert [c.accent for c in clicks[:4]] == [True, False, False, False]
    assert clicks[1].sample == round(beat_samples)
    assert clicks[4].sample == tl.segment(Stage.PLAY).start - round(4 * beat_samples)


def test_expected_notes_are_timed_in_the_play_segment(beat):
    tl = Timeline(beat, start=0, sample_rate=SR)
    expected = tl.expected(lambda sample: sample / SR)
    play_start = tl.segment(Stage.PLAY).start / SR
    assert len(expected) == len(beat.notes)
    assert min(e.time for e in expected) == pytest.approx(play_start)
    assert max(e.time for e in expected) < tl.end / SR


def test_schedule_plays_clicks_and_demo_but_play_segment_is_silent(beat):
    tl = Timeline(beat, start=0, sample_rate=SR)
    mixer = Mixer(SR)
    tl.schedule(mixer, build_kit(SR), build_clicks(SR))
    audio = np.concatenate([mixer.render(1024) for _ in range(tl.end // 1024 + 1)])
    second_count_in = tl.segments[2]
    play = tl.segment(Stage.PLAY)
    # Allow the last demo/click sounds to ring into the start of the next part.
    ring = int(0.6 * SR)
    assert np.max(np.abs(audio[second_count_in.start : second_count_in.end])) > 0.01
    assert np.max(np.abs(audio[play.start + ring : play.end])) < 1e-4


CLICKS = [i * 0.667 for i in range(MEASURED_CLICKS)]


def test_calibration_takes_median_offset_and_one_stray_tap_does_not_fail_it():
    taps = [c + 0.030 + jitter for c, jitter in zip(CLICKS, [0, 0.004, -0.003, 0.2, 0.002, -0.005, 0.001, 0])]
    m = measure(CLICKS, taps)
    assert m.offset == pytest.approx(0.030, abs=0.002)
    assert m.usable


def test_calibration_needs_enough_taps():
    m = measure(CLICKS, [CLICKS[0], CLICKS[1]])
    assert not m.enough_taps
    assert not m.usable


def test_scattered_taps_are_rejected():
    jitter = [0.0, 0.06, -0.05, 0.04, -0.07, 0.05, -0.04, 0.03]
    m = measure(CLICKS, [c + j for c, j in zip(CLICKS, jitter)])
    assert m.enough_taps
    assert m.scatter > MAX_SCATTER
    assert not m.consistent
    assert not m.usable


def test_steady_but_late_taps_are_accepted():
    m = measure(CLICKS, [c + 0.120 + (0.008 if i % 2 else -0.008) for i, c in enumerate(CLICKS)])
    assert m.usable
    assert m.offset == pytest.approx(0.120, abs=0.01)


def test_settings_round_trip_and_tolerate_missing_file(tmp_path):
    path = tmp_path / "s" / "settings.json"
    assert Settings.load(path) == Settings()
    Settings(latency_offset=0.042, calibrated=True).save(path)
    assert Settings.load(path) == Settings(latency_offset=0.042, calibrated=True)


def _triplet_beat():
    from fractions import Fraction as F

    from drum_practice.kit import DrumClass
    from drum_practice.model import Note
    from drum_practice.rhythm import TimeSignature

    notes = [Note(F(i, 3), DrumClass.HH_CLOSED) for i in range(12)] + [Note(F(1), DrumClass.SNARE)]
    return Beat("Shuffle", "Blues", "beginner", 90.0, 1, notes, TimeSignature(4, 4), grid=3)


def test_grading_a_triplet_beat_played_exactly_is_perfect():
    from drum_practice.grading import Played, grade

    tl = Timeline(_triplet_beat(), start=0, sample_rate=SR)
    expected = tl.expected(lambda sample: sample / SR)
    result = grade(expected, [Played(e.time + 0.004, e.drum) for e in expected])
    assert result.score == 100


def test_playing_triplets_as_straight_notes_is_marked_off():
    from fractions import Fraction as F

    from drum_practice.grading import Played, Verdict, grade

    beat = _triplet_beat()
    tl = Timeline(beat, start=0, sample_rate=SR)
    expected = tl.expected(lambda sample: sample / SR)
    play_start = tl.segment(Stage.PLAY).start / SR
    second_triplet = next(e for e in expected if e.at == F(1, 3))
    # Hitting the 16th (1/4) instead of the triplet (1/3): ~56 ms early -> only Good.
    sixteenth = grade([second_triplet], [Played(play_start + beat.seconds(F(1, 4)), second_triplet.drum)])
    assert sixteenth.notes[0].verdict is Verdict.GOOD and sixteenth.notes[0].early
    # Hitting the 8th (1/2) instead: ~111 ms late -> a miss.
    eighth = grade([second_triplet], [Played(play_start + beat.seconds(F(1, 2)), second_triplet.drum)])
    assert eighth.notes[0].verdict is Verdict.MISS
