"""The photo → beat pipeline, with recorded replies and fake clients: no network."""

from fractions import Fraction as F
from types import SimpleNamespace

import pytest

from drum_practice.ai import keys
from drum_practice.ai.evaluate import score, total
from drum_practice.ai.providers import (
    PRICES,
    ClaudeTranscriber,
    GeminiTranscriber,
    OpenAITranscriber,
    TranscriptionError,
    Usage,
    cost,
    friendly_message,
)
from drum_practice.ai.transcription import (
    ALLOWED_DIVISIONS,
    MAX_UNSURE_LINES,
    PhotoReading,
    ReplyError,
    UnsureSpot,
    describe_unsure,
    unsure_cells,
    json_schema,
    parse_reply,
    to_beats,
)
from drum_practice.kit import DrumClass as D
from drum_practice.model import ACCENT, GHOST, MAX_BEAT_BARS, NORMAL, Note
from drum_practice.rhythm import SUBDIVISIONS, TimeSignature

from conftest import FIXTURES

REPLIES = FIXTURES / "ai"


def reply(name: str) -> str:
    return (REPLIES / f"{name}.json").read_text()


# --- the schema matches the app's model ---


def test_schema_drums_are_exactly_the_kits_drums():
    note = json_schema()["$defs"]["NoteReading"]["properties"]
    assert set(note["drum"]["enum"]) == {d.name for d in D}


def test_allowed_divisions_cover_every_editor_subdivision():
    four_four = TimeSignature(4, 4)
    assert {s.columns(four_four) for s in SUBDIVISIONS} <= set(ALLOWED_DIVISIONS)


def test_schema_is_strict_everywhere():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    for obj in objects(json_schema()):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


# --- turning replies into beats ---


def test_a_good_reply_becomes_exact_positions_and_velocities():
    result = to_beats(parse_reply(reply("good_single")), name="Photo")
    (groove,) = result.grooves
    beat = groove.beat
    assert beat.name == "Photo A" and beat.tempo == 80 and beat.bars == 1 and groove.problems == []
    assert Note(F(0), D.KICK, NORMAL) in beat.notes
    assert Note(F(1), D.SNARE, ACCENT) in beat.notes
    assert Note(F(7, 4), D.SNARE, GHOST) in beat.notes  # the "a" of beat 2
    assert Note(F(2) + F(2, 3), D.HH_CLOSED, NORMAL) in beat.notes  # last triplet of beat 3
    assert Note(F(3) + F(5, 8), D.TOM_HIGH, NORMAL) in beat.notes  # a 32nd in beat 4
    assert beat.divisions == {2: 3, 3: 8}  # beat 3 triplets, beat 4 32nds: finer than the 16th grid


def test_several_grooves_become_separate_beats_named_by_label():
    result = to_beats(parse_reply(reply("good_multiple")), name="Funk")
    assert [g.beat.name for g in result.grooves] == ["Funk A", "Funk B", "Funk 3"]
    assert result.grooves[1].beat.notes[0].at == F(1, 2)
    six_eight = result.grooves[2].beat
    assert six_eight.time_signature == TimeSignature(6, 8)
    assert six_eight.notes == [Note(F(3, 2) + F(1, 2), D.RIDE)]  # beat 2 of 6/8, 2nd 8th
    assert [(u.bar, u.beat, u.drum, u.reason) for u in result.unsure] == [(1, 2, "SNARE", "timing"), (1, 4, "SNARE", "timing")]


def test_unsure_spots_become_one_short_line_per_drum_and_reason():
    spot = lambda bar, beat, drum, reason, groove="A": UnsureSpot(groove=groove, bar=bar, beat=beat, drum=drum, reason=reason)
    spots = [spot(1, 4, "SNARE", "timing"), spot(1, 2, "SNARE", "timing"), spot(2, 1, "SNARE", "timing"),
             spot(1, 3, None, "unclear"), spot(1, 1, "KICK", "missing")]
    assert describe_unsure(spots, several_grooves=False) == (
        "AI import was unsure about:\n"
        "• Snare, bar 1 beats 2 and 4, bar 2 beat 1: may be in the wrong place in the beat\n"
        "• Notes, bar 1 beat 3: hard to read in the photo\n"
        "• Kick, bar 1 beat 1: a note may be missing"
    )
    assert describe_unsure([spot(1, 2, "RIDE", "dynamics", groove="B")], several_grooves=True) == (
        "AI import was unsure about:\n• Groove B: Ride, bar 1 beat 2: accent or ghost may be wrong"
    )
    assert describe_unsure([], several_grooves=False) == ""


def test_a_long_unsure_list_is_cut_short():
    spots = [UnsureSpot(groove="", bar=1, beat=1, drum=d, reason="drum") for d in ("KICK", "SNARE", "RIDE", "CRASH", "TOM_HIGH", "TOM_MID", "TOM_LOW")]
    lines = describe_unsure(spots, several_grooves=False).split("\n")
    assert len(lines) == 1 + MAX_UNSURE_LINES + 1 and lines[-1] == "…and 2 more"


def test_free_text_unsure_is_rejected():
    with pytest.raises(ReplyError):
        parse_reply('{"grooves": [], "unsure": "I wasn\'t sure about beat 2."}')


def test_impossible_notes_are_dropped_and_reported():
    result = to_beats(parse_reply(reply("partial")))
    (groove,) = result.grooves
    # The reply said 1 bar but has a note in bar 2: the notes win, so it's 2 bars.
    assert groove.beat.bars == 2 and [n.drum for n in groove.beat.notes] == [D.KICK, D.SNARE]
    assert len(groove.problems) == 3  # beat 5 of 4, division 5, index 4 of 4
    assert groove.beat.tempo == 90.0  # 400 BPM isn't believable: default instead


def test_music_longer_than_a_beat_is_flagged_and_trimmed():
    (groove,) = to_beats(parse_reply(reply("long_song"))).grooves
    assert groove.too_long and groove.bars_read == 6
    assert groove.beat.bars == MAX_BEAT_BARS
    assert all(n.at < groove.beat.total_quarters for n in groove.beat.notes)


@pytest.mark.parametrize("name", ["malformed", "wrong_drum"])
def test_bad_replies_are_rejected_with_a_reply_error(name):
    with pytest.raises(ReplyError):
        parse_reply(reply(name))


def test_a_reply_with_no_grooves_says_so():
    with pytest.raises(ReplyError, match="No drum notation"):
        to_beats(parse_reply(reply("empty")))


def test_bad_time_signature_is_a_reply_error():
    data = parse_reply(reply("good_single")).model_dump()
    data["grooves"][0]["time_signature"] = "4/5"
    with pytest.raises(ReplyError, match="time signature"):
        to_beats(PhotoReading.model_validate(data))


# --- providers send the documented request shapes ---

IMAGE = b"\x89PNG fake"


class Recorder:
    """A fake SDK client that records the call and returns a canned response."""

    def __init__(self, response):
        self.calls = []
        self.response = response

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def claude_client(response):
    create = Recorder(response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, create


def claude_response(text, stop="end_turn"):
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1500, output_tokens=400),
        model="claude-opus-5-5",
    )


def test_claude_request_uses_structured_output_image_and_fallback():
    client, create = claude_client(claude_response(reply("good_single")))
    result = ClaudeTranscriber(client_factory=lambda key: client).read(IMAGE, "image/png", "claude-opus-5-5", "k")
    call = create.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": json_schema()}
    assert call["output_config"]["effort"] == "high"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    image = call["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert parse_reply(result.text).grooves[0].label == "A"
    assert result.usage == Usage(1500, 400)


def test_claude_haiku_gets_no_fallback():
    client, create = claude_client(claude_response(reply("good_single")))
    ClaudeTranscriber(client_factory=lambda key: client).read(IMAGE, "image/png", "claude-haiku-5-5", "k")
    assert "fallbacks" not in create.calls[0] and "betas" not in create.calls[0]


@pytest.mark.parametrize("stop, kind", [("refusal", "refused"), ("max_tokens", "bad_reply")])
def test_claude_stop_reasons_become_clear_errors(stop, kind):
    client, _ = claude_client(claude_response("", stop=stop))
    with pytest.raises(TranscriptionError) as caught:
        ClaudeTranscriber(client_factory=lambda key: client).read(IMAGE, "image/png", "claude-opus-5-5", "k")
    assert caught.value.kind == kind


def test_claude_auth_and_connection_errors_are_translated():
    import anthropic
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def failing(error):
        def create(**kwargs):
            raise error

        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))

    auth = anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=request), body=None)
    offline = anthropic.APIConnectionError(request=request)
    for error, kind in ((auth, "auth"), (offline, "network")):
        with pytest.raises(TranscriptionError) as caught:
            ClaudeTranscriber(client_factory=lambda key, e=error: failing(e)).read(IMAGE, "image/png", "claude-opus-5-5", "k")
        assert caught.value.kind == kind


def test_openai_request_uses_input_image_data_url_and_pydantic_format():
    parsed = parse_reply(reply("good_single"))
    response = SimpleNamespace(output_parsed=parsed, usage=SimpleNamespace(input_tokens=900, output_tokens=300), model="gpt-6-astra")
    parse = Recorder(response)
    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    result = OpenAITranscriber(client_factory=lambda key: client).read(IMAGE, "image/jpeg", "gpt-6-astra", "k")
    call = parse.calls[0]
    assert call["text_format"] is PhotoReading
    image = call["input"][0]["content"][0]
    assert image["type"] == "input_image" and image["image_url"].startswith("data:image/jpeg;base64,")
    assert parse_reply(result.text) == parsed


def test_openai_without_a_parsed_answer_is_refused():
    response = SimpleNamespace(output_parsed=None, usage=None, model="gpt-6-astra")
    client = SimpleNamespace(responses=SimpleNamespace(parse=Recorder(response)))
    with pytest.raises(TranscriptionError) as caught:
        OpenAITranscriber(client_factory=lambda key: client).read(IMAGE, "image/png", "gpt-6-astra", "k")
    assert caught.value.kind == "refused"


def test_gemini_request_uses_interactions_with_json_schema():
    usage = SimpleNamespace(total_input_tokens=700, total_output_tokens=200, total_thought_tokens=50)
    interaction = SimpleNamespace(output_text=reply("good_single"), usage=usage, model="gemini-3.8-flash")
    create = Recorder(interaction)
    client = SimpleNamespace(interactions=SimpleNamespace(create=create))
    result = GeminiTranscriber(client_factory=lambda key: client).read(IMAGE, "image/png", "gemini-3.8-flash", "k")
    call = create.calls[0]
    assert call["response_format"] == {"type": "text", "mime_type": "application/json", "schema": json_schema()}
    kinds = [part["type"] for part in call["input"]]
    assert kinds == ["text", "image"] and call["input"][1]["mime_type"] == "image/png"
    assert result.usage == Usage(700, 250)  # thinking tokens are billed as output


def test_gemini_api_errors_are_translated():
    from google.genai import errors

    def failing(code, message):
        def create(**kwargs):
            raise errors.ClientError(code, {"error": {"code": code, "message": message, "status": "X"}})

        return SimpleNamespace(interactions=SimpleNamespace(create=create))

    for code, message, kind in ((400, "API key not valid. Please pass a valid API key.", "auth"), (429, "Quota exceeded", "rate_limit"), (400, "Bad image", "failed")):
        with pytest.raises(TranscriptionError) as caught:
            GeminiTranscriber(client_factory=lambda key: failing(code, message)).read(IMAGE, "image/png", "gemini-3.8-flash", "k")
        assert caught.value.kind == kind, (code, message)


class _ClosesWhenDropped:
    """Like google-genai's Client: dropping it closes the connection that its
    lazy model listing still needs."""

    def __init__(self):
        self._connection = {"open": True}
        connection = self._connection

        def listing():
            if not connection["open"]:
                raise RuntimeError("Cannot send a request, as the client has been closed.")
            yield "a model"

        self.models = SimpleNamespace(list=listing)

    def __del__(self):
        self._connection["open"] = False


@pytest.mark.parametrize("provider", [ClaudeTranscriber, OpenAITranscriber, GeminiTranscriber])
def test_key_check_keeps_the_client_alive_until_the_listing_is_read(provider):
    provider(client_factory=lambda key: _ClosesWhenDropped()).check_key("k")  # must not raise


def test_every_error_kind_has_a_plain_message():
    for kind in ("no_key", "auth", "network", "rate_limit", "refused", "bad_reply", "failed"):
        text = friendly_message(TranscriptionError(kind, "detail"), "Claude")
        assert "Claude" in text and len(text) < 160


def test_cost_uses_known_prices_and_is_unknown_otherwise():
    assert cost("claude-opus-5-5", Usage(1_000_000, 100_000)) == pytest.approx(PRICES["claude-opus-5-5"][0] + PRICES["claude-opus-5-5"][1] / 10)
    assert cost("gpt-6-astra", Usage(1000, 1000)) is None
    assert cost("claude-opus-5-5", None) is None


# --- keys live in the Keychain (an in-memory stand-in here) ---


@pytest.fixture
def memory_keyring():
    import keyring
    from keyring.backend import KeyringBackend
    from keyring.errors import PasswordDeleteError

    class Memory(KeyringBackend):
        priority = 1
        store: dict = {}

        def get_password(self, service, username):
            return self.store.get((service, username))

        def set_password(self, service, username, password):
            self.store[(service, username)] = password

        def delete_password(self, service, username):
            if (service, username) not in self.store:
                raise PasswordDeleteError()
            del self.store[(service, username)]

    previous = keyring.get_keyring()
    backend = Memory()
    backend.store = {}
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_keys_are_stored_per_provider_and_trimmed(memory_keyring):
    assert not keys.has_key("claude")
    keys.set_key("claude", "  sk-ant-123 \n")
    keys.set_key("openai", "sk-456")
    assert keys.get_key("claude") == "sk-ant-123" and keys.get_key("openai") == "sk-456"
    assert memory_keyring.store[(keys.SERVICE, "claude")] == "sk-ant-123"
    keys.delete_key("claude")
    keys.delete_key("claude")  # deleting twice is harmless
    assert keys.get_key("claude") is None


# --- accuracy scoring for the evaluation script ---


def test_scoring_counts_found_missed_and_invented():
    answer = to_beats(parse_reply(reply("good_single"))).grooves[0].beat
    transcribed = to_beats(parse_reply(reply("good_single"))).grooves[0].beat
    transcribed.notes = transcribed.notes[:-1] + [Note(F(0), D.CRASH)]  # one missed, one invented
    s = score([transcribed], [answer])
    assert (s.expected, s.found, s.missed, s.invented) == (8, 7, 1, 1)
    assert s.precision == pytest.approx(7 / 8) and s.recall == pytest.approx(7 / 8)


def test_scoring_handles_extra_or_missing_grooves():
    beats = [g.beat for g in to_beats(parse_reply(reply("good_multiple"))).grooves]
    s = score(beats[:2], beats)
    assert s.missed == len(beats[2].notes) and s.invented == 0
    assert total([s, s]).expected == 2 * s.expected


def test_rate_limit_messages_include_what_the_provider_said():
    text = friendly_message(TranscriptionError("rate_limit", "Quota exceeded for metric:\n  list_models_requests"), "Gemini")
    assert "list_models_requests" in text and "\n  " not in text
    assert "\n" not in friendly_message(TranscriptionError("rate_limit"), "Gemini")


def test_unsure_spots_map_to_beats_in_the_groove():
    from drum_practice.model import Beat

    beat = Beat(name="x", genre="", difficulty="beginner", tempo=90.0, bars=2, notes=[])
    spots = [UnsureSpot(groove="", bar=1, beat=2, drum="SNARE", reason="timing"),
             UnsureSpot(groove="", bar=2, beat=1, drum=None, reason="unclear"),
             UnsureSpot(groove="", bar=3, beat=1, drum="KICK", reason="missing"),  # past the end
             UnsureSpot(groove="", bar=1, beat=5, drum="KICK", reason="missing")]  # no beat 5 in 4/4
    assert unsure_cells(spots, beat) == {(1, D.SNARE), (4, None)}
