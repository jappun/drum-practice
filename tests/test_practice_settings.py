import pytest

from drum_practice.kit import DrumClass
from drum_practice.model import Beat, Note
from drum_practice.player import click_sample
from drum_practice.session import Stage, Timeline
from drum_practice.settings import Settings

from conftest import FIXTURES

SR = 48_000


def one_bar_beat() -> Beat:
    return Beat.from_dict(
        {
            "name": "t",
            "genre": "Rock",
            "difficulty": "beginner",
            "tempo": 90,
            "bars": 1,
            "pattern": {"KICK": "x--- ---- x--- ----", "SNARE": "---- x--- ---- x---"},
        }
    )


# --- bars ---


def test_with_bars_repeats_a_shorter_pattern():
    beat = one_bar_beat().with_bars(4)
    assert beat.bars == 4
    assert beat.total_steps == 64
    kicks = [n.step for n in beat.notes if n.drum is DrumClass.KICK]
    assert kicks == [0, 8, 16, 24, 32, 40, 48, 56]


def test_with_bars_cuts_a_longer_pattern_to_its_first_bars():
    two_bar = Beat.load(FIXTURES / "rock_open_hat_fill.json")
    one = two_bar.with_bars(1)
    assert one.total_steps == 16
    assert all(n.step < 16 for n in one.notes)
    assert one.notes == [n for n in two_bar.notes if n.step < 16]


def test_with_bars_keeps_velocities_and_leaves_original_alone():
    beat = one_bar_beat()
    beat.notes[0] = Note(0, DrumClass.KICK, 127)
    stretched = beat.with_bars(2)
    assert Note(16, DrumClass.KICK, 127) in stretched.notes
    assert beat.bars == 1 and len(beat.notes) == 4


def test_with_bars_same_length_is_unchanged():
    beat = one_bar_beat()
    assert beat.with_bars(1) == beat


# --- tempo ---


def test_tempo_change_scales_the_whole_timeline():
    beat = one_bar_beat().with_bars(2)
    slow = Timeline(beat.with_tempo(60), 0, SR)
    fast = Timeline(beat.with_tempo(120), 0, SR)
    assert slow.end == 2 * fast.end
    assert slow.note_sample(Stage.PLAY, 4) == 2 * fast.note_sample(Stage.PLAY, 4)


def test_with_tempo_keeps_notes():
    beat = one_bar_beat()
    faster = beat.with_tempo(140)
    assert faster.tempo == 140 and faster.notes == beat.notes
    assert beat.tempo == 90


# --- metronome ---


def test_click_during_your_turn_adds_a_click_per_beat_of_play():
    beat = one_bar_beat().with_bars(2)
    plain = Timeline(beat, 0, SR)
    clicking = Timeline(beat, 0, SR, metronome=True)
    play = clicking.segment(Stage.PLAY)
    extra = [c for c in clicking.clicks() if play.start <= c.sample < play.end]
    assert len(extra) == 8  # 2 bars of 4/4
    assert [c.accent for c in extra] == [True, False, False, False] * 2
    assert len(clicking.clicks()) == len(plain.clicks()) + 8


def test_metronome_off_and_no_count_in_means_no_clicks():
    assert Timeline(one_bar_beat(), 0, SR, count_in=False).clicks() == []


def test_metronome_only_clicks_do_not_drift():
    for tempo in (60, 97, 180):
        for i in (1, 100, 1000):
            assert abs(click_sample(0, tempo, i, SR) - i * 60 / tempo * SR) <= 0.5


# --- persistence ---


def test_practice_settings_persist(tmp_path):
    path = tmp_path / "settings.json"
    Settings(tempo=120, bars=4, count_in=False, metronome=True).save(path)
    loaded = Settings.load(path)
    assert (loaded.tempo, loaded.bars, loaded.count_in, loaded.metronome) == (120, 4, False, True)


def test_old_settings_file_gets_new_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"latency_offset": 0.02, "calibrated": true}')
    loaded = Settings.load(path)
    assert loaded.latency_offset == pytest.approx(0.02)
    assert loaded.count_in is True and loaded.metronome is False and loaded.bars == 2


def test_hidden_examples_persist(tmp_path):
    path = tmp_path / "settings.json"
    Settings(hidden_examples=["example_basic_rock"]).save(path)
    assert Settings.load(path).hidden_examples == ["example_basic_rock"]
    assert Settings.load(tmp_path / "missing.json").hidden_examples == []
