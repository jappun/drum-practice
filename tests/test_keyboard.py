from dataclasses import fields

from drum_practice.keyboard_in import KEY_MAP, drum_for_key, key_label, note_for
from drum_practice.kit import DrumClass, classify
from drum_practice.settings import DevSettings, Settings


def test_every_drum_has_exactly_one_key():
    assert sorted(KEY_MAP.values(), key=lambda d: d.name) == sorted(DrumClass, key=lambda d: d.name)


def test_keys_are_case_insensitive_and_space_is_kick():
    assert drum_for_key("f") is DrumClass.SNARE
    assert drum_for_key("F") is DrumClass.SNARE
    assert drum_for_key(" ") is DrumClass.KICK


def test_unmapped_and_non_character_keys_are_ignored():
    assert drum_for_key("z") is None
    assert drum_for_key("") is None  # e.g. Shift, arrows
    assert drum_for_key("\r") is None


def test_key_labels_are_readable():
    assert key_label(DrumClass.KICK) == "Space"
    assert key_label(DrumClass.SNARE) == "F"


def test_keyboard_hits_use_a_note_the_kit_map_agrees_with():
    for drum in DrumClass:
        assert classify(note_for(drum)) is drum


def test_dev_settings_live_in_their_own_file(tmp_path):
    path = tmp_path / "dev_settings.json"
    DevSettings(keyboard_latency_offset=0.05, keyboard_calibrated=True).save(path)
    assert DevSettings.load(path) == DevSettings(keyboard_latency_offset=0.05, keyboard_calibrated=True)
    assert DevSettings.FILENAME != Settings.FILENAME


def test_regular_settings_have_no_keyboard_fields():
    assert not any("keyboard" in f.name for f in fields(Settings))
