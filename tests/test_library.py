import random

from drum_practice.library import (
    Best,
    ScoreBook,
    is_example,
    search_beats,
    surprise,
    visible_beats,
)
from drum_practice.model import MAX_BEAT_BARS, Beat, load_beats


def make(beat_id: str, name: str | None = None) -> Beat:
    beat = Beat.from_dict(
        {
            "name": name or beat_id,
            "genre": "Rock",
            "difficulty": "beginner",
            "tempo": 90,
            "bars": 1,
            "pattern": {"KICK": "x--- ---- ---- ----"},
        }
    )
    beat.id = beat_id
    return beat


BEATS = [
    make("user_a_1", "Funky Drummer"),
    make("user_b_1", "Rock Groove 10"),
    make("user_c_1", "Rock Groove 2"),
    make("example_basic", "Basic Rock"),
    make("user_d_1", "Half-time shuffle"),
]


# --- search ---


def test_empty_search_lists_everything_in_natural_name_order():
    assert [b.name for b in search_beats(BEATS)] == [
        "Basic Rock",
        "Funky Drummer",
        "Half-time shuffle",
        "Rock Groove 2",
        "Rock Groove 10",
    ]


def test_search_is_case_insensitive_and_partial():
    assert [b.name for b in search_beats(BEATS, "ROCK")] == ["Basic Rock", "Rock Groove 2", "Rock Groove 10"]
    assert [b.name for b in search_beats(BEATS, "funk")] == ["Funky Drummer"]


def test_every_word_must_match_in_any_order():
    assert [b.name for b in search_beats(BEATS, "groove rock 1")] == ["Rock Groove 10"]
    assert search_beats(BEATS, "rock shuffle") == []


def test_surrounding_spaces_are_ignored():
    assert search_beats(BEATS, "  shuffle ") == search_beats(BEATS, "shuffle")


def test_no_match_is_empty():
    assert search_beats(BEATS, "samba") == []


# --- surprise me ---


def test_surprise_picks_from_the_whole_library():
    rng = random.Random(3)
    assert {surprise(BEATS, rng=rng).id for _ in range(200)} == {b.id for b in BEATS}


def test_surprise_avoids_the_current_beat_when_it_can():
    rng = random.Random(2)
    assert all(surprise(BEATS, exclude_id="user_a_1", rng=rng).id != "user_a_1" for _ in range(50))


def test_surprise_returns_the_only_beat_even_if_current():
    only = [make("user_x_1")]
    assert surprise(only, exclude_id="user_x_1").id == "user_x_1"


def test_surprise_with_an_empty_library_is_none():
    assert surprise([]) is None


# --- examples ---


def test_hidden_examples_are_left_out():
    assert [b.id for b in visible_beats(BEATS, ["example_basic"])] == [
        "user_a_1", "user_b_1", "user_c_1", "user_d_1"
    ]


def test_only_examples_can_be_hidden():
    # A stray user-beat id in the hidden list can't make your own beat vanish.
    assert len(visible_beats(BEATS, ["user_a_1"])) == len(BEATS)


def test_restoring_is_an_empty_hidden_list():
    assert visible_beats(BEATS, []) == BEATS


# --- best scores ---


def test_first_run_is_a_best(tmp_path):
    book = ScoreBook(tmp_path / "scores.json")
    assert book.best("r_beg") is None
    assert book.record("r_beg", 70.0, 90, 2)
    assert book.best("r_beg") == Best(70.0, 90, 2)


def test_higher_score_replaces_lower_does_not(tmp_path):
    book = ScoreBook(tmp_path / "scores.json")
    book.record("r_beg", 70.0, 90, 2)
    assert not book.record("r_beg", 65.0, 120, 2)
    assert book.best("r_beg").score == 70.0
    assert book.record("r_beg", 85.5, 80, 1)
    assert book.best("r_beg") == Best(85.5, 80, 1)


def test_tie_goes_to_the_faster_tempo(tmp_path):
    book = ScoreBook(tmp_path / "scores.json")
    book.record("r_beg", 100.0, 90, 2)
    assert not book.record("r_beg", 100.0, 90, 2)  # same run isn't "new"
    assert not book.record("r_beg", 100.0, 80, 2)
    assert book.record("r_beg", 100.0, 110, 2)
    assert book.best("r_beg").tempo == 110


def test_scores_are_per_beat_and_persist(tmp_path):
    path = tmp_path / "sub" / "scores.json"
    book = ScoreBook(path)
    book.record("r_beg", 70.0, 90, 2)
    book.record("f_int", 55.0, 100, 4)
    reloaded = ScoreBook(path)
    assert reloaded.best("r_beg") == Best(70.0, 90, 2)
    assert reloaded.best("f_int") == Best(55.0, 100, 4)


def test_corrupt_scores_file_starts_fresh(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text("not json")
    assert ScoreBook(path).best("anything") is None


def test_old_groove_midi_scores_are_cleared(tmp_path):
    book = ScoreBook(tmp_path / "scores.json")
    book.record("gmd_drummer1_rock_1", 80, 100, 2)
    book.record("user_mine_1", 90, 100, 2)
    book.forget_prefix("gmd_")
    reloaded = ScoreBook(tmp_path / "scores.json")
    assert reloaded.best("gmd_drummer1_rock_1") is None
    assert reloaded.best("user_mine_1") is not None


# --- bundled beats ---

BUNDLED = load_beats()


def test_bundled_library_is_a_few_examples():
    assert 3 <= len(BUNDLED) <= 5
    assert all(is_example(b) for b in BUNDLED)
    assert len({b.id for b in BUNDLED}) == len(BUNDLED)


def test_every_example_is_well_formed():
    for beat in BUNDLED:
        assert beat.name, beat.id
        assert 1 <= beat.bars <= MAX_BEAT_BARS, beat.id
        assert beat.notes, beat.id
        assert all(0 <= n.at < beat.total_quarters for n in beat.notes), beat.id
