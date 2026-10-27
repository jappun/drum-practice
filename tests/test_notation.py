import os
from fractions import Fraction as F
from pathlib import Path

import pytest

from drum_practice.kit import DrumClass as D
from drum_practice.model import ACCENT, Beat, Note, load_beats
from drum_practice.notation.layout import (
    DOWN,
    STAFF_POSITION,
    UP,
    layout_beat,
    beam_groups,
    note_value,
    split_into_values,
    voice_of,
    written_division,
)
from drum_practice.rhythm import TimeSignature

SNAPSHOTS = Path(__file__).parent / "snapshots"


def beat(notes, ts="4/4", bars=1) -> Beat:
    return Beat("t", "Rock", "beginner", 90.0, bars, sorted(notes, key=Note.sort_key), TimeSignature.parse(ts))


def events(layout, voice):
    return [e for per_beat in layout.events[voice] for e in per_beat]


# --- the drum key ---


def test_staff_positions_follow_the_drum_book_key():
    assert STAFF_POSITION[D.KICK] == 1  # bottom space
    assert STAFF_POSITION[D.SNARE] == 5  # third space
    assert STAFF_POSITION[D.HH_CLOSED] == STAFF_POSITION[D.HH_OPEN] == 9  # above the staff
    assert STAFF_POSITION[D.RIDE] == 8  # top line
    assert STAFF_POSITION[D.CRASH] == 10  # ledger line above
    assert STAFF_POSITION[D.HH_PEDAL] == -1  # below the staff
    assert STAFF_POSITION[D.TOM_HIGH] > STAFF_POSITION[D.TOM_MID] > STAFF_POSITION[D.SNARE] > STAFF_POSITION[D.TOM_LOW]


def test_cymbals_get_x_noteheads_and_drums_black_ones():
    layout = layout_beat(beat([Note(F(0), D.HH_CLOSED), Note(F(0), D.SNARE), Note(F(1), D.RIDE), Note(F(2), D.KICK)]))
    kinds = {h.note.drum: h.kind for h in layout.heads if h.note}
    assert kinds[D.HH_CLOSED] == kinds[D.RIDE] == "head:x"
    assert kinds[D.SNARE] == kinds[D.KICK] == "head:black"


def test_crash_gets_a_ledger_line_and_open_hihat_an_o():
    layout = layout_beat(beat([Note(F(0), D.CRASH), Note(F(1), D.HH_OPEN)]))
    assert [pos for _, pos in layout.ledgers] == [10]
    assert any(h.kind == "open" for h in layout.heads)


def test_percussion_staff_has_no_accidentals_or_pitches():
    layout = layout_beat(load_beats()[0])
    assert not any("accidental" in h.kind or "sharp" in h.kind or "flat" in h.kind for h in layout.heads)


# --- voices and stems ---


def test_hands_stem_up_and_feet_stem_down():
    assert voice_of(D.SNARE) == voice_of(D.HH_CLOSED) == UP
    assert voice_of(D.KICK) == voice_of(D.HH_PEDAL) == DOWN
    layout = layout_beat(beat([Note(F(0), D.SNARE), Note(F(0), D.KICK)]))
    for stem in layout.stems:
        assert (stem.end > stem.start) == (stem.voice == UP)


def test_a_chord_shares_one_stem_from_lowest_to_beyond_highest():
    layout = layout_beat(beat([Note(F(0), D.SNARE), Note(F(0), D.HH_CLOSED)]))
    (stem,) = [s for s in layout.stems if s.voice == UP]
    assert stem.start == STAFF_POSITION[D.SNARE] and stem.end > STAFF_POSITION[D.HH_CLOSED]


# --- rhythm ---


@pytest.mark.parametrize("example", load_beats(), ids=lambda b: b.id)
def test_every_voice_of_every_bar_adds_up_to_the_bar(example):
    """Notes and rests in each voice follow on without gaps or overlaps and
    exactly fill every bar, including inside tuplets."""
    layout = layout_beat(example)
    for voice in (UP, DOWN):
        per_beat = layout.events[voice]
        for bar in range(example.bars):
            bar_events = [e for b in per_beat[bar * example.beats_per_bar : (bar + 1) * example.beats_per_bar] for e in b]
            at = bar * example.bar_quarters
            for e in bar_events:
                assert e.at == at, (example.id, voice, bar, e)
                at += e.length
            assert at == (bar + 1) * example.bar_quarters


@pytest.mark.parametrize("ts", ["3/4", "6/8", "7/8", "12/8", "2/2"])
def test_odd_meters_fill_their_bars_too(ts):
    sig = TimeSignature.parse(ts)
    notes = [Note(F(i, 2), D.HH_CLOSED) for i in range(int(sig.bar_quarters * 2))] + [Note(F(0), D.KICK)]
    b = beat(notes, ts=ts)
    layout = layout_beat(b)
    for voice in (UP, DOWN):
        assert sum(e.length for per in layout.events[voice] for e in per) == b.bar_quarters


def test_eighth_note_hats_are_beamed_in_pairs_per_beat():
    hats = [Note(F(i, 2), D.HH_CLOSED) for i in range(8)]
    layout = layout_beat(beat(hats))
    beams = [b for b in layout.beams if b.voice == UP]
    assert [(b.start.quarters, b.end.quarters, b.level) for b in beams] == [
        (F(0), F(1, 2), 1), (F(1), F(3, 2), 1), (F(2), F(5, 2), 1), (F(3), F(7, 2), 1)
    ]


def test_dotted_eighth_and_sixteenth_get_a_partial_beam():
    layout = layout_beat(beat([Note(F(0), D.KICK), Note(F(3, 4), D.KICK)]))
    feet = events(layout, DOWN)[:2]
    assert [(e.value, e.dots) for e in feet] == [(F(1, 2), 1), (F(1, 4), 0)]
    stubs = [b for b in layout.beams if b.stub]
    assert len(stubs) == 1 and stubs[0].level == 2 and stubs[0].start.quarters == F(3, 4)


def test_gaps_become_rests():
    layout = layout_beat(beat([Note(F(1, 2), D.SNARE)]))
    first_beat = layout.events[UP][0]
    assert [(e.is_rest, e.value) for e in first_beat] == [(True, F(1, 2)), (False, F(1, 2))]
    assert all(e.is_rest and e.value == 1 for b in layout.events[UP][1:] for e in b)


def test_a_silent_voice_gets_one_whole_bar_rest():
    layout = layout_beat(beat([Note(F(0), D.SNARE)]))
    (rest,) = events(layout, DOWN)
    assert rest.is_rest and rest.value == 4
    assert [h.kind for h in layout.heads if h.voice == DOWN] == ["rest:whole"]


def test_drums_dont_sustain_so_awkward_lengths_become_note_plus_rest():
    # A note on 1 then one on the "a": 3 16ths -> a dotted 8th (one note);
    # a note on the "e" then nothing: 3 16ths too. But 5 32nds can't be one note.
    layout = layout_beat(beat([Note(F(0), D.SNARE), Note(F(5, 8), D.SNARE)]))
    first = layout.events[UP][0]
    assert [(e.is_rest, e.value, e.dots) for e in first] == [
        (False, F(1, 2), 0), (True, F(1, 8), 0), (False, F(1, 4), 1)
    ]


# --- tuplets ---


def test_triplets_get_a_3_and_8th_note_values():
    layout = layout_beat(beat([Note(F(i, 3), D.HH_CLOSED) for i in range(3)]))
    assert [(t.number, t.start.quarters, t.end.quarters) for t in layout.tuplets] == [(3, F(0), F(2, 3))]
    assert [e.value for e in layout.events[UP][0]] == [F(1, 2)] * 3  # written as 8ths


def test_shuffle_is_quarter_eighth_under_a_3():
    layout = layout_beat(beat([Note(F(0), D.RIDE), Note(F(2, 3), D.RIDE)]))
    assert [e.value for e in layout.events[UP][0]] == [F(1), F(1, 2)]
    assert layout.tuplets[0].number == 3


def test_sixteenth_triplets_are_a_6():
    layout = layout_beat(beat([Note(F(i, 6), D.SNARE) for i in range(6)]))
    assert layout.tuplets[0].number == 6
    assert all(e.value == F(1, 4) for e in layout.events[UP][0])


def test_compound_time_needs_no_tuplet_for_eighths():
    layout = layout_beat(beat([Note(F(i, 2), D.HH_CLOSED) for i in range(6)], ts="6/8"))
    assert layout.tuplets == []
    assert [len(b) for b in layout.events[UP]] == [3, 3]


def test_written_division():
    assert written_division(compound=False, columns=4) == (4, None)
    assert written_division(compound=False, columns=3) == (2, 3)  # 8th triplets
    assert written_division(compound=False, columns=6) == (4, 6)  # 16th triplets
    assert written_division(compound=True, columns=1) == (3, None)  # a lone note: dotted quarter
    assert written_division(compound=True, columns=2) == (6, None)  # two dotted 8ths, no duplet needed
    assert written_division(compound=True, columns=4) == (12, None)  # four dotted 16ths, no tuplet
    assert written_division(compound=True, columns=5) == (3, 5)  # five in a beat really is a tuplet


def test_a_lone_note_in_compound_time_is_a_dotted_quarter_with_no_tuplet():
    layout = layout_beat(beat([Note(F(0), D.KICK), Note(F(3, 2), D.SNARE)], ts="6/8"))
    assert layout.tuplets == []
    assert [(e.value, e.dots) for e in layout.events[DOWN][0]] == [(F(1), 1)]


@pytest.mark.parametrize("ts, groups", [("4/4", [1, 1, 1, 1]), ("6/8", [1, 1]), ("7/8", [2, 2, 3]), ("5/8", [2, 3]), ("3/8", [3])])
def test_beam_groups(ts, groups):
    assert beam_groups(TimeSignature.parse(ts)) == groups


def test_seven_eight_eighths_beam_two_two_three():
    layout = layout_beat(beat([Note(F(i, 2), D.RIDE) for i in range(7)], ts="7/8"))
    spans = [(b.start.quarters, b.end.quarters) for b in layout.beams if b.voice == UP]
    assert spans == [(F(0), F(1, 2)), (F(1), F(3, 2)), (F(2), F(3))]
    assert not any(h.kind.startswith("flag") for h in layout.heads)


def test_beams_dont_join_a_triplet_beat_to_a_straight_one():
    layout = layout_beat(beat([Note(F(i, 2), D.RIDE) for i in range(2)] + [Note(F(1) + F(i, 3), D.RIDE) for i in range(3)], ts="2/8"))
    # 2/8: one beam group of two 8th beats; beat 2 is triplets, so beams stay separate.
    spans = [(b.start.quarters, b.end.quarters) for b in layout.beams if b.level == 1]
    assert (F(0), F(1, 2)) in spans and all(not (s < 1 <= e) for s, e in spans)


def test_note_values():
    assert note_value(F(3, 4)) == (F(1, 2), 1)
    assert note_value(F(5, 8)) is None
    assert split_into_values(F(3, 4)) == [(F(1, 2), 1)]
    assert split_into_values(F(5, 4)) == [(F(1), 0), (F(1, 4), 0)]


# --- snapshots of the examples ---


@pytest.mark.parametrize("example", load_beats(), ids=lambda b: b.id)
def test_example_layout_matches_snapshot(example):
    """The engraving of each example. If a change is intended, regenerate with
    UPDATE_SNAPSHOTS=1 pytest tests/test_notation.py and review the diff."""
    path = SNAPSHOTS / f"{example.id}.txt"
    text = layout_beat(example).describe()
    if os.environ.get("UPDATE_SNAPSHOTS") or not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
    assert text == path.read_text()


def test_accented_notes_are_still_ordinary_noteheads():
    # Dynamics marks come in a later phase; accents shouldn't change the engraving yet.
    plain = layout_beat(beat([Note(F(0), D.SNARE)])).describe()
    accented = layout_beat(beat([Note(F(0), D.SNARE, ACCENT)])).describe()
    assert plain == accented


# --- rests stay clear of the other voice ---

def _rest_heads(layout, voice):
    return [h for h in layout.heads if h.kind.startswith("rest") and h.voice == voice]


def _clear_of(layout, rest, others):
    """The rest's glyph doesn't reach any of the other voice's noteheads."""
    from drum_practice.notation.layout import REST_EXTENT

    above, below = REST_EXTENT[rest.kind.split(":")[1]]
    top, bottom = rest.position + above, rest.position - below
    return all(not (bottom <= pos + 1 and pos - 1 <= top) for pos in others)


def test_a_kick_rest_moves_below_the_snare_it_sits_under():
    # Kick on 1 and 3; snare on 2 and 4: the kick voice rests on 2 and 4.
    b = beat([Note(F(0), D.KICK), Note(F(2), D.KICK), Note(F(1), D.SNARE), Note(F(3), D.SNARE)])
    layout = layout_beat(b)
    rests = _rest_heads(layout, DOWN)
    assert len(rests) == 2
    for rest in rests:
        assert _clear_of(layout, rest, [STAFF_POSITION[D.SNARE]])


def test_rests_stay_put_when_the_other_voice_is_silent():
    from drum_practice.notation.layout import REST_POSITION

    layout = layout_beat(beat([Note(F(0), D.KICK), Note(F(2), D.KICK)]))
    assert all(h.position == REST_POSITION[DOWN] for h in _rest_heads(layout, DOWN) if h.kind != "rest:whole")


def test_hand_rests_move_above_a_low_foot_note():
    # A floor-tom-free bar where the hands rest over a kick: hand rests sit above it.
    layout = layout_beat(beat([Note(F(0), D.KICK), Note(F(1), D.KICK), Note(F(1, 2), D.SNARE)]))
    for rest in _rest_heads(layout, UP):
        assert _clear_of(layout, rest, [STAFF_POSITION[D.KICK]])


@pytest.mark.parametrize("example", load_beats(), ids=lambda b: b.id)
def test_no_rest_in_the_examples_collides_with_the_other_voice(example):
    layout = layout_beat(example)
    for rest in [h for h in layout.heads if h.kind.startswith("rest")]:
        events = [e for per in layout.events[rest.voice] for e in per if e.is_rest]
        span = next((e for e in events if e.at <= rest.x.quarters < e.at + e.length), None)
        if span is None:
            continue
        others = [
            STAFF_POSITION[n.drum]
            for n in example.notes
            if voice_of(n.drum) != rest.voice and span.at <= n.at < span.at + span.length
        ]
        assert _clear_of(layout, rest, others), (example.id, rest)

