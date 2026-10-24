import random

import pytest

from drum_practice.library import DIFFICULTIES, Best, ScoreBook, filter_beats, genres, surprise
from drum_practice.model import Beat, load_beats


def make(beat_id: str, genre: str, difficulty: str, name: str | None = None) -> Beat:
    beat = Beat.from_dict(
        {
            "name": name or beat_id,
            "genre": genre,
            "difficulty": difficulty,
            "tempo": 90,
            "bars": 1,
            "pattern": {"KICK": "x--- ---- ---- ----"},
        }
    )
    beat.id = beat_id
    return beat


BEATS = [
    make("r_adv", "Rock", "advanced"),
    make("r_beg", "Rock", "beginner"),
    make("f_int", "Funk", "intermediate"),
    make("f_beg", "Funk", "beginner"),
    make("d_beg", "Disco", "beginner"),
]


# --- filtering ---


def test_no_filters_lists_everything_easiest_first():
    ids = [b.id for b in filter_beats(BEATS)]
    assert ids[:3] == ["d_beg", "f_beg", "r_beg"]  # beginners, by name
    assert ids[3:] == ["f_int", "r_adv"]


def test_genre_filter():
    assert {b.id for b in filter_beats(BEATS, genre="Rock")} == {"r_adv", "r_beg"}


def test_difficulty_filter():
    assert {b.id for b in filter_beats(BEATS, difficulty="beginner")} == {"r_beg", "f_beg", "d_beg"}


def test_both_filters():
    assert [b.id for b in filter_beats(BEATS, "Funk", "intermediate")] == ["f_int"]
    assert filter_beats(BEATS, "Disco", "advanced") == []


def test_genres_are_unique_and_sorted():
    assert genres(BEATS) == ["Disco", "Funk", "Rock"]


# --- surprise me ---


def test_surprise_respects_filters():
    rng = random.Random(1)
    for _ in range(50):
        pick = surprise(BEATS, genre="Rock", rng=rng)
        assert pick.genre == "Rock"
        pick = surprise(BEATS, difficulty="beginner", rng=rng)
        assert pick.difficulty == "beginner"


def test_surprise_avoids_the_current_beat_when_it_can():
    rng = random.Random(2)
    assert all(surprise(BEATS, genre="Rock", exclude_id="r_beg", rng=rng).id == "r_adv" for _ in range(20))


def test_surprise_returns_the_only_match_even_if_current():
    assert surprise(BEATS, "Funk", "intermediate", exclude_id="f_int").id == "f_int"


def test_surprise_with_no_matches_is_none():
    assert surprise(BEATS, "Disco", "advanced") is None


def test_surprise_eventually_picks_every_match():
    rng = random.Random(3)
    assert {surprise(BEATS, difficulty="beginner", rng=rng).id for _ in range(100)} == {"r_beg", "f_beg", "d_beg"}


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


# --- bundled beats ---


def test_bundled_library_covers_genres_and_all_difficulties():
    beats = load_beats()
    assert 8 <= len(beats) <= 10
    assert len(genres(beats)) >= 2
    assert {b.difficulty for b in beats} == set(DIFFICULTIES)
    assert len({b.id for b in beats}) == len(beats)
    assert all(b.id for b in beats)


@pytest.mark.parametrize("beat", load_beats(), ids=lambda b: b.id)
def test_every_bundled_beat_is_well_formed(beat):
    assert beat.difficulty in DIFFICULTIES
    assert beat.notes, "beat has no notes"
    if beat.id == "funk_linear":
        steps = [n.step for n in beat.notes]
        assert len(steps) == len(set(steps)), "linear groove has two voices on one step"
