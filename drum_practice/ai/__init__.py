"""AI features, provider-agnostic. Today: reading a beat from a photo.

Providers (Claude, OpenAI, Gemini, and later a hosted service) sit behind
the `Transcriber` interface in `providers`, so the rest of the app never
depends on which one is used.
"""
