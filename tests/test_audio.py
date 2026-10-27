import numpy as np
import pytest

from drum_practice.audio import MASTER_GAIN, Mixer
from drum_practice.kit import DrumClass
from drum_practice.model import Beat
from drum_practice.player import beat_events
from drum_practice.sounds import build_kit

from conftest import FIXTURES

SR = 48_000
IMPULSE = np.zeros(64, dtype=np.float32)
IMPULSE[0] = 1.0


def _render(mixer: Mixer, total: int, block: int) -> np.ndarray:
    chunks = []
    while sum(len(c) for c in chunks) < total:
        chunks.append(mixer.render(block))
    return np.concatenate(chunks)[:total]


def _onsets(signal: np.ndarray) -> list[int]:
    return [int(i) for i in np.flatnonzero(np.abs(signal) > 1e-6)]


@pytest.mark.parametrize("block", [37, 256, 512, 4096])
def test_scheduled_sounds_start_on_exact_sample_regardless_of_block_size(block):
    mixer = Mixer(SR)
    for sample in [0, 100, 255, 256, 1000, 9999]:
        mixer.schedule(sample, IMPULSE)
    assert _onsets(_render(mixer, 12_000, block)) == [0, 100, 255, 256, 1000, 9999]


def test_beat_renders_with_every_note_within_1ms_of_its_position():
    beat = Beat.load(FIXTURES / "rock_open_hat_fill.json")
    start = 4_800
    events = beat_events(beat, start, SR)
    mixer = Mixer(SR)
    for sample, _ in events:
        mixer.schedule(sample, IMPULSE)
    rendered = _render(mixer, start + int(beat.duration_seconds * SR) + 100, 512)

    expected = sorted({start + beat.seconds(n.at) * SR for n in beat.notes})
    onsets = _onsets(rendered)
    assert len(onsets) == len(expected)
    for got, want in zip(onsets, expected):
        assert abs(got - want) / SR < 0.001


def test_later_loops_do_not_drift():
    beat = Beat.from_dict(
        {"name": "t", "genre": "g", "difficulty": "beginner", "tempo": 93, "bars": 1,
         "pattern": {"KICK": "x--- ---- ---- ----"}}
    )
    loop_seconds = beat.duration_seconds
    for loop in [1, 10, 100]:
        (sample, _), = beat_events(beat, 0, SR, loop=loop)
        assert abs(sample - loop * loop_seconds * SR) <= 0.5


def test_choke_cuts_ringing_voice_quickly():
    mixer = Mixer(SR)
    long_tone = np.ones(SR, dtype=np.float32)
    mixer.schedule(0, long_tone, group=DrumClass.HH_OPEN)
    mixer.schedule(1_000, IMPULSE * 0, group=DrumClass.HH_CLOSED, chokes=DrumClass.HH_OPEN)
    out = _render(mixer, SR, 512)
    assert out[999] == pytest.approx(np.tanh(MASTER_GAIN))
    assert np.all(out[1_000 + int(0.01 * SR):] == 0)


def test_late_sound_plays_whole_instead_of_losing_its_attack():
    mixer = Mixer(SR)
    mixer.render(1_000)
    mixer.schedule(500, IMPULSE)  # already in the past
    assert _onsets(mixer.render(512)) == [0]


def test_choke_does_not_silence_a_voice_that_starts_after_it():
    mixer = Mixer(SR)
    tone = np.ones(100, dtype=np.float32)
    mixer.schedule(10, IMPULSE * 0, group=DrumClass.HH_CLOSED, chokes=DrumClass.HH_OPEN)
    mixer.schedule(200, tone, group=DrumClass.HH_OPEN)
    out = mixer.render(512)
    assert np.all(out[200:300] > 0)


def test_clear_drops_pending_sounds():
    mixer = Mixer(SR)
    mixer.schedule(5_000, IMPULSE)
    mixer.render(512)
    mixer.clear()
    assert not _onsets(_render(mixer, 10_000, 512))


def test_synth_kit_has_a_sound_for_every_drum_and_stays_in_range():
    kit = build_kit(SR)
    assert set(kit) == set(DrumClass)
    for sound in kit.values():
        assert sound.dtype == np.float32
        assert 0.1 < np.max(np.abs(sound)) <= 1.5


def test_triplets_and_32nds_render_within_1ms():
    from fractions import Fraction as F

    from drum_practice.model import Note
    from drum_practice.rhythm import TimeSignature

    hats = [Note(F(i, 3), DrumClass.HH_CLOSED) for i in range(12)]  # 8th triplets
    fill = [Note(F(3) + F(i, 8), DrumClass.SNARE) for i in range(8)]  # 32nds in beat 4
    beat = Beat("t", "g", "beginner", 97.0, 1, hats[:9] + fill, TimeSignature(4, 4))
    start = 1_000
    mixer = Mixer(SR)
    for sample, _ in beat_events(beat, start, SR):
        mixer.schedule(sample, IMPULSE)
    onsets = _onsets(_render(mixer, start + int(beat.duration_seconds * SR) + 100, 512))
    expected = sorted(start + beat.seconds(n.at) * SR for n in beat.notes)
    assert len(onsets) == len(expected)
    assert max(abs(got - want) for got, want in zip(onsets, expected)) / SR < 0.001
