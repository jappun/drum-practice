from pathlib import Path

from drum_practice.ui import theme

OLD_ORANGE = ("#f2a541", "#ffe7b8")


def test_accent_is_purple():
    assert theme.ACCENT.lower() == "#8742f5"


def test_no_orange_left_anywhere_in_the_app():
    package = Path(theme.__file__).resolve().parent.parent
    for path in package.rglob("*.py"):
        text = path.read_text().lower()
        for colour in OLD_ORANGE:
            assert colour not in text, f"{colour} in {path.name}"


def _contrast(fg: str, bg: str) -> float:
    def lum(h: str) -> float:
        def chan(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_on_and_around_the_accent_is_readable():
    assert _contrast(theme.ON_ACCENT, theme.ACCENT) >= 4.5
    assert _contrast(theme.ACCENT_TEXT, theme.BG) >= 4.5
