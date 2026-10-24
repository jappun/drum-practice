import random
from collections import Counter

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


def test_numbered_names_sort_naturally():
    beats = [make(f"r{n}", "Rock", "beginner", name=f"Rock {n}") for n in (10, 2, 1, 100)]
    assert [b.name for b in filter_beats(beats)] == ["Rock 1", "Rock 2", "Rock 10", "Rock 100"]


def test_other_genre_sorts_last():
    beats = [make("o", "Other", "beginner"), make("a", "Afrobeat", "beginner"), make("p", "Punk", "beginner")]
    assert genres(beats) == ["Afrobeat", "Punk", "Other"]


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


BUNDLED = load_beats()


def test_bundled_library_covers_genres_and_all_difficulties():
    assert len(BUNDLED) > 100
    assert len(genres(BUNDLED)) >= 5
    counts = Counter(b.difficulty for b in BUNDLED)
    assert set(counts) == set(DIFFICULTIES)
    assert max(counts.values()) - min(counts.values()) <= 1  # split into even thirds
    assert len({b.id for b in BUNDLED}) == len(BUNDLED)


def test_every_bundled_beat_is_well_formed():
    for beat in BUNDLED:
        assert beat.id and beat.name, beat.id
        assert beat.difficulty in DIFFICULTIES, beat.id
        assert beat.bars == 2 and len(beat.notes) >= 16, beat.id
        assert all(0 <= n.step < beat.total_steps for n in beat.notes), beat.id
