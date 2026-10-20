import mido

from drum_practice.kit import DRUM_ORDER, NOTE_MAP, DrumClass, classify
from drum_practice.midi_in import Hit, RawMessage, message_to_event


def test_core_gm_notes_map_to_expected_drums():
    assert classify(36) is DrumClass.KICK
    assert classify(38) is DrumClass.SNARE
    assert classify(42) is DrumClass.HH_CLOSED
    assert classify(46) is DrumClass.HH_OPEN
    assert classify(44) is DrumClass.HH_PEDAL
    assert classify(49) is DrumClass.CRASH
    assert classify(51) is DrumClass.RIDE


def test_every_drum_class_has_a_note_and_a_display_slot():
    assert set(NOTE_MAP.values()) == set(DrumClass)
    assert set(DRUM_ORDER) == set(DrumClass)
    assert len(DRUM_ORDER) == len(DrumClass) == 10


def test_unknown_note_is_reported_not_crashed_on():
    assert classify(99) is None
    event = message_to_event(mido.Message("note_on", note=99, velocity=80), now=1.0)
    assert event == Hit(note=99, velocity=80, time=1.0, drum=None)


def test_note_on_becomes_hit_with_velocity():
    event = message_to_event(mido.Message("note_on", note=38, velocity=17), now=2.5)
    assert event == Hit(note=38, velocity=17, time=2.5, drum=DrumClass.SNARE)


def test_note_offs_and_zero_velocity_note_ons_are_ignored():
    assert message_to_event(mido.Message("note_off", note=38), now=0) is None
    assert message_to_event(mido.Message("note_on", note=38, velocity=0), now=0) is None


def test_hihat_pedal_position_cc_is_kept_as_raw_message():
    event = message_to_event(mido.Message("control_change", control=4, value=127), now=3.0)
    assert isinstance(event, RawMessage)
    assert "control=4" in event.text
