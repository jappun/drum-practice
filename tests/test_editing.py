from fractions import Fraction

from drum_practice.editing import (
    Stroke,
    blank,
    click,
    duplicate,
    note_at,
    paint,
    resize,
    same_music,
    set_beat_columns,
    set_grid,
    set_time_signature,
)
from drum_practice.kit import DrumClass
from drum_practice.library import ScoreBook, UserBeats, is_user_beat
from drum_practice.model import ACCENT, GHOST, MAX_BEAT_BARS, NORMAL, Beat, Note
from drum_practice.rhythm import TimeSignature

S, K = DrumClass.SNARE, DrumClass.KICK
F = Fraction


# --- clicking and painting ---


def test_click_on_empty_cell_adds_a_note_with_the_brush():
    beat, stroke = click(blank(), 4, S, GHOST)
    assert beat.notes == [Note(4, S, GHOST)]
    assert stroke is Stroke.ADD


def test_click_on_a_matching_note_removes_it():
    beat, _ = click(blank(), 4, S, NORMAL)
    beat, stroke = click(beat, 4, S, NORMAL)
    assert beat.notes == []
    assert stroke is Stroke.REMOVE


def test_click_on_a_different_strength_changes_it_to_the_brush():
    beat, _ = click(blank(), 4, S, NORMAL)
    beat, stroke = click(beat, 4, S, ACCENT)
    assert beat.notes == [Note(4, S, ACCENT)]
    assert stroke is Stroke.ADD


def test_click_only_touches_that_drum_on_that_step():
    beat, _ = click(blank(), 0, K, NORMAL)
    beat, _ = click(beat, 0, S, NORMAL)
    beat, _ = click(beat, 0, S, NORMAL)
    assert beat.notes == [Note(0, K, NORMAL)]


def test_drag_repeats_the_stroke():
    beat = blank()
    eighths = [F(i, 2) for i in range(4)]
    for at in eighths:
        beat = paint(beat, at, S, Stroke.ADD, NORMAL)
    assert [n.at for n in beat.notes] == eighths
    beat = paint(beat, F(1, 2), S, Stroke.REMOVE, NORMAL)
    beat = paint(beat, F(3, 4), S, Stroke.REMOVE, NORMAL)  # removing an empty cell is harmless
    assert [n.at for n in beat.notes] == [0, 1, F(3, 2)]


def test_triplet_positions_are_exact_cells():
    beat, _ = click(blank(), F(1, 3), S, NORMAL)
    beat, stroke = click(beat, F(1, 3), S, NORMAL)
    assert beat.notes == [] and stroke is Stroke.REMOVE


def test_edits_return_new_beats_and_leave_the_original_alone():
    original = blank()
    edited, _ = click(original, 0, K, NORMAL)
    assert original.notes == [] and edited.notes


def test_notes_stay_sorted():
    beat = blank()
    for step, drum in [(8, S), (0, S), (0, K), (4, K)]:
        beat, _ = click(beat, step, drum, NORMAL)
    assert beat.notes == sorted(beat.notes, key=Note.sort_key)
    assert note_at(beat, 0, K) == Note(0, K, NORMAL)


# --- length ---


def test_resize_adds_empty_bars_and_cuts_removed_ones():
    beat, _ = click(blank(), F(15, 2), S, NORMAL)  # in bar 2
    beat, _ = click(beat, F(1, 2), K, NORMAL)
    beat.divisions = {7: 3}
    longer = resize(beat, 4)
    assert longer.total_quarters == 16 and longer.notes == beat.notes and longer.divisions == {7: 3}
    shorter = resize(beat, 1)
    assert shorter.total_quarters == 4 and shorter.notes == [Note(F(1, 2), K, NORMAL)]
    assert shorter.divisions == {}


def test_resize_is_clamped():
    assert resize(blank(), 0).bars == 1
    assert resize(blank(), 9).bars == MAX_BEAT_BARS


# --- grid and time signature ---


def test_set_grid_divides_every_beat_and_snaps_notes():
    beat, _ = click(blank(), F(1, 4), S, NORMAL)  # the "e" of 1, a 16th
    beat.divisions = {2: 8}
    triplets, moved = set_grid(beat, 3)
    assert triplets.grid == 3 and triplets.divisions == {}
    assert [n.at for n in triplets.notes] == [F(1, 3)]  # nearest triplet
    assert moved == 1


def test_set_grid_leaves_fitting_notes_alone():
    beat, _ = click(blank(), F(1, 2), S, NORMAL)
    sixteenth_triplets, moved = set_grid(beat, 6)
    assert sixteenth_triplets.notes == beat.notes and moved == 0


def test_set_beat_columns_changes_one_beat_only():
    beat, _ = click(blank(), F(1, 4), S, NORMAL)
    beat, _ = click(beat, F(3) + F(1, 4), S, NORMAL)  # same spot in beat 4
    changed, moved = set_beat_columns(beat, 3, 3)
    assert changed.divisions == {3: 3}
    assert [n.at for n in changed.notes] == [F(1, 4), F(3) + F(1, 3)]
    assert moved == 1
    back, _ = set_beat_columns(changed, 3, changed.grid)
    assert back.divisions == {}


def test_snapping_two_notes_onto_one_cell_keeps_the_louder():
    beat, _ = click(blank(), F(3, 8), S, GHOST)  # 32nds either side of the "&"
    beat, _ = click(beat, F(5, 8), S, ACCENT)
    snapped, _ = set_grid(beat, 2)  # 8ths
    assert snapped.notes == [Note(F(1, 2), S, ACCENT)]


def test_set_time_signature_resets_the_grid_and_drops_overflow():
    beat, _ = click(blank(), F(7), S, NORMAL)  # in bar 2 of 4/4 (ends at 8)
    beat, _ = click(beat, F(1), K, NORMAL)
    beat.divisions = {1: 3}
    three_four, moved = set_time_signature(beat, TimeSignature(3, 4))
    assert three_four.total_quarters == 6 and [n.at for n in three_four.notes] == [1]
    assert three_four.divisions == {} and three_four.grid == 4 and moved == 0
    six_eight, _ = set_time_signature(beat, TimeSignature(6, 8))
    assert six_eight.grid == 6  # 16ths per dotted-quarter beat


def test_set_time_signature_snaps_notes_that_no_longer_fit():
    beat, _ = click(blank(), F(3) + F(1, 3), S, NORMAL)  # a triplet in 4/4
    six_eight, moved = set_time_signature(beat, TimeSignature(6, 8))
    assert [n.at for n in six_eight.notes] == [F(3) + F(1, 4)] and moved == 1
    assert all(six_eight.columns_in_beat(i) == 6 for i in range(six_eight.total_beats))


# --- copies and comparisons ---


def test_duplicate_is_a_new_unsaved_copy():
    beat, _ = click(blank("Groove"), 0, K, NORMAL)
    beat.id = "gmd_something"
    copy = duplicate(beat)
    assert copy.id == "" and copy.name == "Groove (copy)" and copy.notes == beat.notes
    copy.notes.append(Note(4, S))
    assert len(beat.notes) == 1  # the original's note list isn't shared


def test_same_music_ignores_name_and_tempo_but_not_notes_or_length():
    a, _ = click(blank("A"), 0, K, NORMAL)
    b = Beat(**{**a.__dict__, "name": "B", "tempo": 140.0})
    assert same_music(a, b)
    assert not same_music(a, resize(a, 4))
    assert not same_music(a, click(a, 4, S, NORMAL)[0])


# --- saving user beats ---


def test_user_beats_save_with_a_new_id_and_load_back_identically(tmp_path):
    store = UserBeats(tmp_path)
    beat, _ = click(blank("My Groove!"), 0, K, ACCENT)
    saved = store.save(beat)
    assert saved.id == "user_my_groove_1" and is_user_beat(saved)
    (loaded,) = store.load()
    assert loaded == saved and loaded.id == saved.id


def test_saving_again_keeps_the_id_and_overwrites(tmp_path):
    store = UserBeats(tmp_path)
    saved = store.save(click(blank("Groove"), 0, K, NORMAL)[0])
    edited = store.save(click(saved, 4, S, NORMAL)[0])
    assert edited.id == saved.id
    assert len(store.load()) == 1 and len(store.load()[0].notes) == 2


def test_same_name_gets_a_distinct_id(tmp_path):
    store = UserBeats(tmp_path)
    first = store.save(blank("Groove"))
    second = store.save(blank("Groove"))
    assert first.id != second.id


def test_duplicating_a_library_beat_saves_as_a_user_beat(tmp_path):
    library_beat = blank("Rock 5")
    library_beat.id = "gmd_drummer1_rock"
    saved = UserBeats(tmp_path).save(duplicate(library_beat))
    assert is_user_beat(saved) and saved.id != library_beat.id


def test_delete_removes_the_file(tmp_path):
    store = UserBeats(tmp_path)
    saved = store.save(blank())
    store.delete(saved.id)
    assert store.load() == []


def test_a_damaged_user_file_is_skipped(tmp_path):
    store = UserBeats(tmp_path)
    store.save(blank("Good"))
    (tmp_path / "user_bad_1.json").write_text("{ not json")
    assert [b.name for b in store.load()] == ["Good"]


def test_missing_folder_means_no_user_beats(tmp_path):
    assert UserBeats(tmp_path / "nope").load() == []


def test_forget_drops_a_best_score(tmp_path):
    book = ScoreBook(tmp_path / "scores.json")
    book.record("user_x_1", 90, 100, 2)
    book.forget("user_x_1")
    assert book.best("user_x_1") is None
    assert ScoreBook(tmp_path / "scores.json").best("user_x_1") is None
