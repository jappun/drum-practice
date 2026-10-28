"""API keys, kept in the macOS Keychain (via `keyring`), never in plain files."""

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "Drum Practice"


def get_key(provider: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, provider) or None
    except KeyringError:
        return None


def set_key(provider: str, key: str) -> None:
    keyring.set_password(SERVICE, provider, key.strip())


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider)
    except PasswordDeleteError:
        pass  # nothing stored


def has_key(provider: str) -> bool:
    return get_key(provider) is not None
