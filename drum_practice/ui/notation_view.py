"""Draws a beat's notation layout with the Bravura music font (SMuFL).

All the engraving decisions live in `notation.layout`; this only turns its
positions into pixels and adds the playhead, highlighting and results.
"""

from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..grading import Verdict
from ..model import Beat
from ..notation.layout import STAFF_POSITION, UP, Layout, X, layout_beat
from . import theme
from .grid import GridResults

FONT_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "Bravura.otf"

SPACE = 10.0  # pixels per staff space
ABOVE = 7.0  # staff spaces above the top line (crash ledger, stems, tuplets)
BELOW = 6.5  # staff spaces below the bottom line (pedal stems, tuplets)
PREFIX = 7.5  # staff spaces for clef, time signature and the opening repeat
BAR_PAD = 2.0  # staff spaces before a bar's first note…
BAR_TAIL = 1.5  # …and after its last, so notes never touch bar lines
RIGHT_MARGIN = 0.5

# SMuFL code points.
GLYPHS = {
    "clef": "",
    "head:black": "",
    "head:black:half": "",
    "head:x": "",
    "head:x:half": "",
    "rest:whole": "",
    "rest:half": "",
    "rest:quarter": "",
    "rest:8th": "",
    "rest:16th": "",
    "rest:32nd": "",
    "rest:64th": "",
    "flag:8th:up": "",
    "flag:8th:down": "",
    "flag:16th:up": "",
    "flag:16th:down": "",
    "flag:32nd:up": "",
    "flag:32nd:down": "",
    "flag:64th:up": "",
    "flag:64th:down": "",
    "dot": "",
    "open": "",
}
TIME_SIG_DIGIT = 0xE080
TUPLET_DIGIT = 0xE880

STEM_WIDTH = 0.12
BEAM_THICKNESS = 0.5
BEAM_GAP = 0.25
STUB_LENGTH = 1.1
STAFF_LINE = 0.13
LEDGER_EXTRA = 0.4  # how far a ledger line reaches past the notehead on each side

_family: str | None = None


def music_font_family() -> str:
    """Load Bravura once and return its family name."""
    global _family
    if _family is None:
        font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise RuntimeError(f"couldn't load the music font from {FONT_PATH}")
        _family = families[0]
    return _family


class NotationView(QWidget):
    def __init__(self):
        super().__init__()
        self.beat: Beat | None = None
        self.layout_: Layout | None = None
        self.results: GridResults | None = None
        self._position: float | None = None
        self._font = QFont(music_font_family())
        self._font.setPixelSize(round(4 * SPACE))  # SMuFL: 1 em = 4 staff spaces
        self._metrics = QFontMetricsF(self._font)
        self.setFixedHeight(int((ABOVE + 4 + BELOW) * SPACE))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # --- same interface as BeatGrid for showing a beat ---

    def set_beat(self, beat: Beat | None) -> None:
        self.beat = beat
        self.layout_ = layout_beat(beat) if beat is not None else None
        self.results = None
        self._position = None
        self.update()

    def set_results(self, results: GridResults | None) -> None:
        self.results = results
        self.update()

    def set_position(self, quarters: float | None) -> None:
        if quarters != self._position:
            self._position = quarters
            self.update()

    # --- geometry ---

    def _staff_bottom(self) -> float:
        return (ABOVE + 4) * SPACE

    def y_of(self, position: float) -> float:
        return self._staff_bottom() - position * SPACE / 2

    def _quarter_px(self) -> float:
        b = self.beat
        fixed = (PREFIX + RIGHT_MARGIN + b.bars * (BAR_PAD + BAR_TAIL)) * SPACE
        return max(1.0, (self.width() - fixed) / float(b.total_quarters))

    def _bar_left(self, bar: int) -> float:
        b = self.beat
        return PREFIX * SPACE + bar * ((BAR_PAD + BAR_TAIL) * SPACE + float(b.bar_quarters) * self._quarter_px())

    def x_of_time(self, quarters: float | Fraction) -> float:
        b = self.beat
        bar = min(int(Fraction(quarters) // b.bar_quarters), b.bars - 1)
        return self._bar_left(bar) + BAR_PAD * SPACE + (float(quarters) - float(bar * b.bar_quarters)) * self._quarter_px()

    def x_of(self, x: X) -> float:
        return self.x_of_time(x.quarters) + x.offset * SPACE

    # --- drawing ---

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        if self.layout_ is None:
            return
        ink = QColor(theme.TEXT)
        self._draw_staff(p)
        self._draw_prefix(p, ink)
        self._draw_bar_lines(p, ink)
        self._draw_playhead(p)

        lit = self._lit_notes()
        verdicts = self.results.notes if self.results else {}
        layout = self.layout_

        for x, position in layout.ledgers:
            cx = self.x_of(x)
            half = (1.18 / 2 + LEDGER_EXTRA) * SPACE
            p.setPen(QPen(QColor(theme.TEXT_DIM), STAFF_LINE * SPACE * 1.3))
            p.drawLine(QPointF(cx - half, self.y_of(position)), QPointF(cx + half, self.y_of(position)))

        for stem in layout.stems:
            x = self._stem_x(stem.x, stem.voice)
            p.setPen(QPen(ink, STEM_WIDTH * SPACE))
            p.drawLine(QPointF(x, self.y_of(stem.start)), QPointF(x, self.y_of(stem.end)))

        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        for beam in layout.beams:
            self._draw_beam(p, beam)

        p.setFont(self._font)
        for head in layout.heads:
            color = ink
            if head.note is not None:
                graded = verdicts.get((head.note.at, head.note.drum))
                if graded is not None:
                    color = QColor(
                        theme.OK if graded.verdict is Verdict.PERFECT
                        else theme.BAD if graded.verdict is Verdict.MISS
                        else theme.ACCENT_TEXT
                    )
                elif head.note in lit:
                    color = QColor(theme.LIT)
            elif head.kind.startswith(("rest", "dot", "flag", "open")):
                color = ink if not head.kind.startswith("rest") else QColor(theme.TEXT_DIM)
            self._draw_glyph(p, head.kind, head.x, head.position, color, voice=head.voice)
            if head.note is not None and verdicts.get((head.note.at, head.note.drum)) is not None:
                self._draw_timing_tick(p, head, verdicts[(head.note.at, head.note.drum)])

        for tuplet in layout.tuplets:
            centre = (self._stem_x(tuplet.start, tuplet.voice) + self._stem_x(tuplet.end, tuplet.voice)) / 2
            text = "".join(chr(TUPLET_DIGIT + int(d)) for d in str(tuplet.number))
            width = self._metrics.horizontalAdvance(text)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QPointF(centre - width / 2, self.y_of(tuplet.position) + (SPACE * 0.75 if tuplet.voice == UP else SPACE * 1.3)), text)

        if self.results:
            self._draw_extras(p)

    def _draw_staff(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(theme.TEXT_DIM), STAFF_LINE * SPACE))
        right = self._bar_left(self.beat.bars)
        for line in range(5):
            y = self.y_of(line * 2)
            p.drawLine(QPointF(SPACE * 0.5, y), QPointF(right, y))

    def _draw_prefix(self, p: QPainter, ink: QColor) -> None:
        p.setFont(self._font)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QPointF(SPACE * 1.0, self.y_of(4)), GLYPHS["clef"])
        ts = self.beat.time_signature
        p.setPen(ink)
        for value, position in ((ts.numerator, 6), (ts.denominator, 2)):
            text = "".join(chr(TIME_SIG_DIGIT + int(d)) for d in str(value))
            width = self._metrics.horizontalAdvance(text)
            p.drawText(QPointF(SPACE * 4.0 - width / 2, self.y_of(position)), text)

    def _draw_bar_lines(self, p: QPainter, ink: QColor) -> None:
        top, bottom = self.y_of(8), self.y_of(0)
        thin, thick = 0.16 * SPACE, 0.5 * SPACE
        b = self.beat
        for quarters, kind in self.layout_.bar_lines:
            bar = int(quarters / b.bar_quarters)
            if kind == "repeat-start":
                x = PREFIX * SPACE - SPACE * 1.0
                self._fill_bar(p, x, thick, ink)
                self._fill_bar(p, x + thick + 0.4 * SPACE, thin, ink)
                self._repeat_dots(p, x + thick + 0.4 * SPACE + thin + 0.55 * SPACE, ink)
            elif kind == "repeat-end":
                x = self._bar_left(bar)
                self._fill_bar(p, x - thick, thick, ink)
                self._fill_bar(p, x - thick - 0.4 * SPACE - thin, thin, ink)
                self._repeat_dots(p, x - thick - 0.4 * SPACE - thin - 0.55 * SPACE, ink)
            else:
                p.setPen(QPen(QColor(theme.TEXT_DIM), thin))
                x = self._bar_left(bar)
                p.drawLine(QPointF(x, top), QPointF(x, bottom))

    def _fill_bar(self, p: QPainter, x: float, width: float, ink: QColor) -> None:
        p.fillRect(QRectF(x, self.y_of(8), width, self.y_of(0) - self.y_of(8)), ink)

    def _repeat_dots(self, p: QPainter, x: float, ink: QColor) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        r = 0.22 * SPACE
        for position in (3, 5):
            p.drawEllipse(QPointF(x, self.y_of(position)), r, r)

    def _draw_playhead(self, p: QPainter) -> None:
        if self._position is None or not 0 <= self._position < self.beat.total_quarters:
            return
        x = self.x_of_time(self._position)
        color = QColor(theme.ACCENT)
        color.setAlphaF(0.85)
        p.setPen(QPen(color, 2))
        p.drawLine(QPointF(x, self.y_of(13)), QPointF(x, self.y_of(-8)))

    def _lit_notes(self) -> set:
        """Notes sounding at the playhead: from their start to the next column."""
        if self._position is None:
            return set()
        pos = Fraction(self._position).limit_denominator(1000)
        b = self.beat
        return {n for n in b.notes if n.at <= pos < n.at + b.column_length(b.beat_index(n.at))}

    def _head_width(self, kind: str) -> float:
        glyph = GLYPHS.get(kind)
        return self._metrics.horizontalAdvance(glyph) if glyph else 1.18 * SPACE

    def _draw_glyph(self, p: QPainter, kind: str, x: X, position: float, color: QColor, voice: int) -> None:
        glyph = GLYPHS.get(kind)
        if glyph is None:
            return
        cx = self.x_of(x)
        if kind.startswith("flag"):
            left = self._stem_x(x, voice) - STEM_WIDTH * SPACE / 2
        elif kind == "dot":
            left = cx  # the layout already placed the dot beside its notehead
        else:
            left = cx - self._metrics.horizontalAdvance(glyph) / 2
        p.setPen(color)
        p.drawText(QPointF(left, self.y_of(position)), glyph)

    def _stem_x(self, x: X, voice: int) -> float:
        """Up stems attach to the right of the notehead, down stems to the left."""
        half = 1.18 * SPACE / 2 - STEM_WIDTH * SPACE / 2
        return self.x_of(x) + (half if voice == UP else -half)

    def _draw_beam(self, p: QPainter, beam) -> None:
        voice = beam.voice
        # Beams hang from the stem tips towards the noteheads, one under another.
        inward = -1 if voice == UP else 1  # staff direction towards the notes
        step = (BEAM_THICKNESS + BEAM_GAP) * 2 * (beam.level - 1)
        tip = beam.position + inward * step
        y1 = self.y_of(tip)
        y2 = self.y_of(tip + inward * BEAM_THICKNESS * 2)
        x1 = self._stem_x(beam.start, voice)
        x2 = self._stem_x(beam.end, voice)
        if beam.stub:
            x2 = x1 + beam.stub * STUB_LENGTH * SPACE
        left, right = sorted((x1, x2))
        p.drawRect(QRectF(left - STEM_WIDTH * SPACE / 2, min(y1, y2), right - left + STEM_WIDTH * SPACE, abs(y2 - y1)))

    def _draw_timing_tick(self, p: QPainter, head, graded) -> None:
        """Good notes get a small wedge on the side they were off: left early, right late."""
        if graded.verdict is not Verdict.GOOD:
            return
        cx, cy = self.x_of(head.x), self.y_of(head.position)
        side = -1 if graded.early else 1
        x = cx + side * 1.05 * SPACE
        path = QPainterPath(QPointF(x, cy - 0.45 * SPACE))
        path.lineTo(x + side * 0.55 * SPACE, cy)
        path.lineTo(x, cy + 0.45 * SPACE)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT_TEXT))
        p.drawPath(path)

    def _draw_extras(self, p: QPainter) -> None:
        r = 0.6 * SPACE
        for marks, color in ((self.results.ignored, theme.TEXT_DIM), (self.results.extras, theme.BAD)):
            p.setPen(QPen(QColor(color), 1.6))
            p.setBrush(Qt.NoBrush)
            for quarters, drum in marks:
                q = min(max(quarters, 0.0), float(self.beat.total_quarters) - 1e-6)
                p.drawEllipse(QPointF(self.x_of_time(q), self.y_of(STAFF_POSITION[drum])), r, r)

