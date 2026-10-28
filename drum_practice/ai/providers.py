"""AI vision providers behind one interface.

Each provider takes a prepared image (bytes + MIME type) and returns the raw
JSON text of a `PhotoReading` (see `transcription`). Everything provider-
specific (SDK calls, request shapes, errors) stays in this file, so a hosted
service can be added later as one more `Transcriber` without UI changes.

Request shapes follow each provider's official SDK documentation:
- Claude: Anthropic SDK, structured outputs via output_config.format, and
  server-side refusal fallbacks (fallbacks="default").
- OpenAI: Responses API, client.responses.parse with a Pydantic text_format.
- Gemini: google-genai Interactions API with a JSON-schema response_format.
"""

import base64
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .transcription import INSTRUCTIONS, PhotoReading, json_schema

ASK = "Transcribe the drum notation in this image."


class TranscriptionError(Exception):
    """A provider call failed. `kind` drives the message the user sees."""

    NO_KEY, AUTH, NETWORK, RATE_LIMIT, REFUSED, BAD_REPLY, FAILED = (
        "no_key", "auth", "network", "rate_limit", "refused", "bad_reply", "failed"
    )

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Reply:
    text: str  # JSON matching PhotoReading
    model: str
    usage: Usage | None
    seconds: float


class Transcriber(Protocol):
    name: str  # stable id, also the Keychain account name
    label: str  # shown to the user
    models: list[str]  # first is the default

    def read(self, image: bytes, mime: str, model: str, api_key: str) -> Reply: ...

    def check_key(self, api_key: str) -> None:
        """Raise TranscriptionError if the key doesn't work. Must not cost anything."""
        ...


def _b64(image: bytes) -> str:
    return base64.standard_b64encode(image).decode("ascii")


def _first_model(client) -> object:
    """List one model: a free request that proves the key works. The client
    is held in a variable until the listing is read, because some SDKs (e.g.
    google-genai) close a client as soon as nothing refers to it, and the
    listing fetches lazily."""
    return next(iter(client.models.list()), None)


def _timed(call: Callable[[], tuple[str, str, Usage | None]]) -> Reply:
    start = time.perf_counter()
    text, model, usage = call()
    return Reply(text, model, usage, time.perf_counter() - start)


# --- Claude ---------------------------------------------------------------


class ClaudeTranscriber:
    name = "claude"
    label = "Claude (Anthropic)"
    models = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    effort = "high"  # reading notation is accuracy-sensitive
    # Server-side refusal fallback (Anthropic picks the retry model by refusal
    # category). Claude Haiku 5.5 has no server-side fallback, so it's left off there.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    NO_FALLBACK = {"claude-haiku-5-5"}

    def __init__(self, client_factory=None):
        import anthropic

        self._anthropic = anthropic
        self._client = client_factory or (lambda key: anthropic.Anthropic(api_key=key))

    def read(self, image: bytes, mime: str, model: str, api_key: str) -> Reply:
        def call():
            extra = {} if model in self.NO_FALLBACK else {"betas": [self.FALLBACK_BETA], "fallbacks": "default"}
            client = self._client(api_key)  # kept until the call finishes (see _first_model)
            response = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=INSTRUCTIONS,
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": json_schema()}},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": _b64(image)}},
                            {"type": "text", "text": ASK},
                        ],
                    }
                ],
                **extra,
            )
            if response.stop_reason == "refusal":
                raise TranscriptionError(TranscriptionError.REFUSED, "Claude declined to read this image.")
            if response.stop_reason == "max_tokens":
                raise TranscriptionError(TranscriptionError.BAD_REPLY, "The reply was cut off before it finished.")
            text = next((b.text for b in response.content if b.type == "text"), None)
            if text is None:
                raise TranscriptionError(TranscriptionError.BAD_REPLY, "Claude returned no text.")
            usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
            return text, response.model, usage

        return self._guard(lambda: _timed(call))

    def check_key(self, api_key: str) -> None:
        self._guard(lambda: _first_model(self._client(api_key)))

    def _guard(self, fn):
        a = self._anthropic
        try:
            return fn()
        except TranscriptionError:
            raise
        except (a.AuthenticationError, a.PermissionDeniedError) as e:
            raise TranscriptionError(TranscriptionError.AUTH, e.message) from e
        except a.RateLimitError as e:
            raise TranscriptionError(TranscriptionError.RATE_LIMIT, e.message) from e
        except a.APIConnectionError as e:  # includes timeouts
            raise TranscriptionError(TranscriptionError.NETWORK, str(e)) from e
        except a.APIStatusError as e:
            raise TranscriptionError(TranscriptionError.FAILED, f"{e.status_code}: {e.message}") from e


# --- OpenAI ---------------------------------------------------------------


class OpenAITranscriber:
    name = "openai"
    label = "OpenAI (GPT)"
    models = ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"]

    def __init__(self, client_factory=None):
        import openai

        self._openai = openai
        self._client = client_factory or (lambda key: openai.OpenAI(api_key=key))

    def read(self, image: bytes, mime: str, model: str, api_key: str) -> Reply:
        def call():
            client = self._client(api_key)  # kept until the call finishes (see _first_model)
            response = client.responses.parse(
                model=model,
                instructions=INSTRUCTIONS,
                input=[
                    {
                        "role": "user",
                        "content": [
                            # "high" detail: noteheads and ledger lines are small.
                            {"type": "input_image", "image_url": f"data:{mime};base64,{_b64(image)}", "detail": "high"},
                            {"type": "input_text", "text": ASK},
                        ],
                    }
                ],
                text_format=PhotoReading,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise TranscriptionError(TranscriptionError.REFUSED, "The model didn't return a transcription.")
            usage = Usage(response.usage.input_tokens, response.usage.output_tokens) if response.usage else None
            return parsed.model_dump_json(), response.model, usage

        return self._guard(lambda: _timed(call))

    def check_key(self, api_key: str) -> None:
        self._guard(lambda: _first_model(self._client(api_key)))

    def _guard(self, fn):
        o = self._openai
        try:
            return fn()
        except TranscriptionError:
            raise
        except (o.AuthenticationError, o.PermissionDeniedError) as e:
            raise TranscriptionError(TranscriptionError.AUTH, e.message) from e
        except o.RateLimitError as e:
            raise TranscriptionError(TranscriptionError.RATE_LIMIT, e.message) from e
        except o.APIConnectionError as e:  # includes timeouts
            raise TranscriptionError(TranscriptionError.NETWORK, str(e)) from e
        except o.APIStatusError as e:
            raise TranscriptionError(TranscriptionError.FAILED, f"{e.status_code}: {e.message}") from e


# --- Gemini ---------------------------------------------------------------


class GeminiTranscriber:
    name = "gemini"
    label = "Google Gemini"
    models = ["gemini-3.8-flash", "gemini-4-argon", "gemini-3.5-flash-lite"]

    def __init__(self, client_factory=None):
        from google import genai
        from google.genai import errors

        self._errors = errors
        self._client = client_factory or (lambda key: genai.Client(api_key=key))

    def read(self, image: bytes, mime: str, model: str, api_key: str) -> Reply:
        def call():
            client = self._client(api_key)  # kept until the call finishes (see _first_model)
            interaction = client.interactions.create(
                model=model,
                input=[
                    {"type": "text", "text": f"{INSTRUCTIONS}\n\n{ASK}"},
                    {"type": "image", "data": _b64(image), "mime_type": mime},
                ],
                response_format={"type": "text", "mime_type": "application/json", "schema": json_schema()},
            )
            text = interaction.output_text
            if not text:
                raise TranscriptionError(TranscriptionError.REFUSED, "Gemini returned no transcription.")
            u = interaction.usage
            usage = Usage(u.total_input_tokens or 0, (u.total_output_tokens or 0) + (u.total_thought_tokens or 0)) if u else None
            return text, interaction.model or model, usage

        return self._guard(lambda: _timed(call))

    def check_key(self, api_key: str) -> None:
        self._guard(lambda: _first_model(self._client(api_key)))

    def _guard(self, fn):
        try:
            return fn()
        except TranscriptionError:
            raise
        except self._errors.APIError as e:
            message = getattr(e, "message", None) or str(e)
            if e.code in (401, 403) or (e.code == 400 and "api key" in message.lower()):
                raise TranscriptionError(TranscriptionError.AUTH, message) from e
            if e.code == 429:
                raise TranscriptionError(TranscriptionError.RATE_LIMIT, message) from e
            raise TranscriptionError(TranscriptionError.FAILED, f"{e.code}: {message}") from e
        except OSError as e:  # connection failures
            raise TranscriptionError(TranscriptionError.NETWORK, str(e)) from e
        except Exception as e:  # the SDK's HTTP library raises its own connect/timeout errors
            if "connect" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower():
                raise TranscriptionError(TranscriptionError.NETWORK, str(e)) from e
            raise


PROVIDERS: dict[str, type] = {
    "claude": ClaudeTranscriber,
    "openai": OpenAITranscriber,
    "gemini": GeminiTranscriber,
}

# Prices in USD per million tokens (input, output), for the cost column of the
# evaluation script. Claude's are Anthropic's published first-party rates;
# OpenAI and Gemini rates aren't listed here, so cost shows as unknown for them.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def cost(model: str, usage: Usage | None) -> float | None:
    if usage is None or model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000


def provider_says(error: TranscriptionError, limit: int = 300) -> str:
    """The provider's own words, shortened, so the user can tell which limit they hit."""
    detail = " ".join(error.detail.split())
    if not detail:
        return ""
    return f"\n{detail[:limit]}{'…' if len(detail) > limit else ''}"


def friendly_message(error: TranscriptionError, provider_label: str) -> str:
    """What to tell the user, by kind of failure."""
    return {
        TranscriptionError.NO_KEY: f"No API key for {provider_label}. Add one in Settings, or enter the notes by hand.",
        TranscriptionError.AUTH: f"{provider_label} didn't accept the API key. Check it in Settings.",
        TranscriptionError.NETWORK: f"Couldn't reach {provider_label}. Check your internet connection and try again.",
        TranscriptionError.RATE_LIMIT: f"{provider_label} is limiting requests right now. Try again in a minute."
        + provider_says(error),
        TranscriptionError.REFUSED: f"{provider_label} wouldn't read this image. Try a clearer crop, another provider, or enter it by hand.",
        TranscriptionError.BAD_REPLY: f"{provider_label}'s answer couldn't be used ({error.detail}). Try again or crop more tightly.",
    }.get(error.kind, f"{provider_label} failed: {error.detail}")
