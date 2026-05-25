"""Design system: токены палитры, типографики, отступов + сборка QSS."""

import sys

# Палитра (dark mode OLED)
BG_PRIMARY = "#020617"  # slate-950 (окно)
BG_SECONDARY = "#0F172A"  # slate-900 (панели)
BG_TERTIARY = "#1E293B"  # slate-800 (контролы)
BG_HOVER = "#334155"  # slate-700
TEXT_PRIMARY = "#F8FAFC"  # slate-50
TEXT_SECONDARY = "#CBD5E1"  # slate-300
TEXT_MUTED = "#64748B"  # slate-500
BORDER = "#1E293B"
BORDER_FOCUS = "#3B82F6"  # blue-500
ACCENT_REC = "#EF4444"  # red-500 (REC активна)
ACCENT_READY = "#22C55E"  # green-500 (готов)
ACCENT_WARNING = "#F59E0B"  # amber-500 (drop frames)
ACCENT_INFO = "#3B82F6"  # blue-500

# Типографика — платформо-зависимые системные шрифты.
# Гарантированно установлены в ОС, избегают Qt warning "Populating font family aliases".
if sys.platform == "darwin":
    FONT_UI = '"SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif'
    FONT_MONO = '"SF Mono", Menlo, Monaco, monospace'
elif sys.platform == "win32":
    FONT_UI = '"Segoe UI", Arial, sans-serif'
    FONT_MONO = '"Cascadia Mono", Consolas, "Courier New", monospace'
else:
    FONT_UI = 'Cantarell, Ubuntu, "DejaVu Sans", "Liberation Sans", sans-serif'
    FONT_MONO = '"DejaVu Sans Mono", "Ubuntu Mono", "Liberation Mono", monospace'
FONT_SIZE_SM = 11
FONT_SIZE_MD = 13
FONT_SIZE_LG = 15

# Отступы (4px scale)
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24

# Радиусы скругления
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14


def build_stylesheet() -> str:
    """Сборка QSS для всего приложения на основе токенов.

    Returns:
        Строка QSS, готовая для передачи в QApplication.setStyleSheet().
    """
    return f"""
    QMainWindow {{
        background-color: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
    }}

    QWidget {{
        background-color: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        font-family: {FONT_UI};
        font-size: {FONT_SIZE_MD}px;
    }}

    QLabel {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        padding: {SPACING_XS}px;
    }}

    QLabel[role="muted"] {{
        color: {TEXT_MUTED};
    }}

    QLabel[role="mono"] {{
        font-family: {FONT_MONO};
        color: {TEXT_SECONDARY};
    }}

    QPushButton {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: {SPACING_SM}px {SPACING_MD}px;
        font-family: {FONT_UI};
        font-size: {FONT_SIZE_MD}px;
        min-height: 28px;
    }}

    QPushButton:hover {{
        background-color: {BG_HOVER};
        border-color: {BORDER_FOCUS};
    }}

    QPushButton:pressed {{
        background-color: {BG_SECONDARY};
    }}

    QPushButton:disabled {{
        background-color: {BG_SECONDARY};
        color: {TEXT_MUTED};
        border-color: {BORDER};
    }}

    QPushButton[role="rec"] {{
        background-color: {ACCENT_REC};
        color: {TEXT_PRIMARY};
        border-color: {ACCENT_REC};
        font-weight: 600;
    }}

    QPushButton[role="rec"]:hover {{
        background-color: #DC2626;
    }}

    QPushButton[role="stop"] {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border-color: {BORDER_FOCUS};
        font-weight: 600;
    }}

    QPushButton[role="stop"]:hover {{
        background-color: {BG_HOVER};
        border-color: {BORDER_FOCUS};
    }}

    QComboBox {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: {SPACING_XS}px {SPACING_SM}px;
        min-height: 24px;
        min-width: 140px;
    }}

    QComboBox:hover {{
        border-color: {BORDER_FOCUS};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {BG_SECONDARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_FOCUS};
        selection-background-color: {BG_HOVER};
        selection-color: {TEXT_PRIMARY};
        padding: {SPACING_XS}px;
    }}

    QSlider::groove:horizontal {{
        background-color: {BG_TERTIARY};
        height: 4px;
        border-radius: 2px;
    }}

    QSlider::handle:horizontal {{
        background-color: {ACCENT_INFO};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}

    QSlider::handle:horizontal:hover {{
        background-color: #2563EB;
    }}

    QSlider::sub-page:horizontal {{
        background-color: {ACCENT_INFO};
        border-radius: 2px;
    }}

    QStatusBar {{
        background-color: {BG_SECONDARY};
        color: {TEXT_SECONDARY};
        border-top: 1px solid {BORDER};
        font-family: {FONT_MONO};
        font-size: {FONT_SIZE_SM}px;
        padding: {SPACING_XS}px {SPACING_SM}px;
    }}

    QStatusBar::item {{
        border: none;
    }}

    QLineEdit {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: {SPACING_XS}px {SPACING_SM}px;
        min-height: 24px;
        selection-background-color: {BORDER_FOCUS};
        selection-color: {TEXT_PRIMARY};
    }}

    QLineEdit:focus {{
        border-color: {BORDER_FOCUS};
    }}

    QLineEdit:disabled {{
        background-color: {BG_SECONDARY};
        color: {TEXT_MUTED};
    }}

    QSpinBox {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: {SPACING_XS}px {SPACING_SM}px;
        min-height: 24px;
        selection-background-color: {BORDER_FOCUS};
        selection-color: {TEXT_PRIMARY};
    }}

    QSpinBox:focus {{
        border-color: {BORDER_FOCUS};
    }}

    QSpinBox:disabled {{
        background-color: {BG_SECONDARY};
        color: {TEXT_MUTED};
    }}

    /* Скрываем нативные стрелки QSpinBox/QDoubleSpinBox: не вписываются в
       скруглённые бордеры. Ввод доступен через клавиатуру и колесо мыши. */
    QSpinBox::up-button,
    QSpinBox::down-button,
    QDoubleSpinBox::up-button,
    QDoubleSpinBox::down-button {{
        width: 0px;
        height: 0px;
        border: none;
        background: transparent;
    }}

    QDoubleSpinBox {{
        background-color: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: {SPACING_XS}px {SPACING_SM}px;
        min-height: 24px;
        selection-background-color: {BORDER_FOCUS};
        selection-color: {TEXT_PRIMARY};
    }}

    QDoubleSpinBox:focus {{
        border-color: {BORDER_FOCUS};
    }}

    QDoubleSpinBox:disabled {{
        background-color: {BG_SECONDARY};
        color: {TEXT_MUTED};
    }}

    QGroupBox {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_LG}px;
        margin-top: {SPACING_MD}px;
        padding: {SPACING_MD}px {SPACING_SM}px {SPACING_SM}px {SPACING_SM}px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {SPACING_MD}px;
        padding: 0 {SPACING_SM}px;
        color: {TEXT_SECONDARY};
    }}

    QScrollArea {{
        background-color: transparent;
        border: none;
    }}

    QCheckBox {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        spacing: {SPACING_SM}px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        background-color: {BG_TERTIARY};
    }}

    QCheckBox::indicator:hover {{
        border-color: {BORDER_FOCUS};
    }}

    QCheckBox::indicator:checked {{
        background-color: {ACCENT_INFO};
        border-color: {ACCENT_INFO};
    }}

    QCheckBox::indicator:disabled {{
        background-color: {BG_SECONDARY};
        border-color: {BORDER};
    }}
    """
