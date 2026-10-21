"""Shared colours and the app-wide Qt stylesheet."""

BG = "#15171c"
SURFACE = "#1e2128"
SURFACE_HI = "#272b34"
BORDER = "#323743"
TEXT = "#e6e8ee"
TEXT_DIM = "#8b92a3"
ACCENT = "#f2a541"
LIT = "#ffe7b8"
OK = "#4cc38a"
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
    color: {BG};
    border: none;
    font-weight: 600;
    padding: 8px 22px;
}}
QPushButton#primary:hover {{
    background: {LIT};
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
QLabel#rowTitle {{
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
    color: {ACCENT};
    min-height: 28px;
}}
QLabel#summary {{
    font-size: 14px;
    line-height: 150%;
}}
"""
