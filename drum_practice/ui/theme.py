"""Shared colours and the app-wide Qt stylesheet."""

BG = "#15171c"
SURFACE = "#1e2128"
SURFACE_HI = "#272b34"
BORDER = "#323743"
TEXT = "#e6e8ee"
TEXT_DIM = "#8b92a3"
ACCENT = "#8742f5"  # buttons, notes, borders, playhead
ACCENT_HOVER = "#9a5cf7"
ON_ACCENT = "#ffffff"  # text on accent fills (5.1:1 contrast)
ACCENT_TEXT = "#a77bf8"  # accent-coloured text on the dark background (5.8:1)
ACCENT_TINT = "#2a2140"  # a faint purple fill behind boxed notes
LIT = "#d9c6fd"  # a note lighting up as it plays
OK = "#4cc38a"
CHECK = "#f5dc7a"  # light yellow: spots the AI asks you to check
BAD = "#e5534b"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QLabel#title {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel#sectionTitle {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#status {{
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 600;
}}
QTableWidget, QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    selection-background-color: {SURFACE_HI};
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: 600;
}}
QPushButton {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton#primary {{
    background: {ACCENT};
    color: {ON_ACCENT};
    border: none;
    font-weight: 600;
    padding: 8px 22px;
}}
QPushButton#primary:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#primary:disabled {{
    background: {SURFACE_HI};
    color: {TEXT_DIM};
}}
QPushButton#segment:checked {{
    background: {ACCENT};
    color: {ON_ACCENT};
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton#danger {{
    color: {BAD};
}}
QPushButton#danger:hover {{
    border-color: {BAD};
}}
QComboBox {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 220px;
}}
QLabel#meta {{
    color: {TEXT_DIM};
}}
QPushButton:disabled, QCheckBox:disabled, QLabel:disabled {{
    color: {TEXT_DIM};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QLineEdit {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 4px;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit#search {{
    padding: 7px 10px;
}}
QPushButton#link {{
    background: transparent;
    border: none;
    color: {ACCENT_TEXT};
    padding: 2px;
}}
QPushButton#link:hover {{
    text-decoration: underline;
}}
QLabel#rowTitle {{
    font-weight: 600;
}}
QLabel#sectionHeading {{
    font-size: 15px;
    font-weight: 600;
}}
QComboBox#filter {{
    min-width: 0px;
}}
QListWidget#library {{
    padding: 4px;
}}
QListWidget#library::item {{
    border-radius: 6px;
    margin: 1px 0px;
}}
QListWidget#library::item:selected {{
    background: {SURFACE_HI};
    border: 1px solid {ACCENT};
}}
QListWidget#library::item:hover:!selected {{
    background: {SURFACE_HI};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: none;
}}
QLabel#beatName {{
    font-weight: 600;
}}
QLabel#bestScore {{
    color: {OK};
    font-weight: 600;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {SURFACE_HI};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QLabel#banner {{
    font-size: 18px;
    font-weight: 600;
    color: {ACCENT_TEXT};
    min-height: 28px;
}}
QLabel#summary {{
    font-size: 14px;
    line-height: 150%;
}}
QLabel#aiNote {{
    background: {ACCENT_TINT};
    border: 1px solid {ACCENT};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}}
QLabel#photo {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QPushButton#choice {{
    text-align: left;
    padding: 14px 18px;
    font-size: 14px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    border: none;
}}
"""
