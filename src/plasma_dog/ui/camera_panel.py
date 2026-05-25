"""CameraSettingsPanel: панель UVC-слайдеров и автогалок для управления камерой."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from plasma_dog.camera.capture import CaptureThread
from plasma_dog.camera.properties import (
    CameraProperty,
    auto_property_values,
    property_default,
    property_range,
)
from plasma_dog.ui.style import FONT_UI, TEXT_MUTED

# Fallback диапазон для слайдеров параметров без зарегистрированного range.
# Используется только если property_range(prop) вернёт None для slider-kind.
_FALLBACK_SLIDER_RANGE = (-100, 100)

# Толерантность сравнения float-значения с auto-значением для чекбоксов.
_AUTO_VALUE_TOLERANCE = 0.5

# Геометрия строки слайдера: длина слайдера и ширины спинбокса/reset-кнопки.
_SLIDER_MIN_WIDTH = 160
_SPINBOX_MAX_WIDTH = 75
# Кнопка сброса: явный текст вместо Unicode-стрелки — на macOS с системным
# шрифтом мелкие символы плохо различимы. Ширина с запасом под русский текст.
_RESET_BUTTON_MIN_WIDTH = 72
_RESET_BUTTON_MAX_WIDTH = 90
_RESET_BUTTON_TEXT = "Сброс"


def _is_auto_value(prop: CameraProperty, value: float) -> bool:
    """Проверка соответствия значения auto-состоянию для данного параметра."""
    _, auto_val = auto_property_values(prop)
    return abs(value - auto_val) < _AUTO_VALUE_TOLERANCE


def _checkbox_emit_value(prop: CameraProperty, checked: bool) -> float:
    """Платформозависимое значение для эмита из чекбокса AUTO_*."""
    manual_val, auto_val = auto_property_values(prop)
    return auto_val if checked else manual_val


# Группы свойств в порядке отображения сверху вниз.
# Каждая группа: (title, [(prop, kind)]) где kind — 'slider' | 'checkbox' | 'readonly'
_GROUPS: list[tuple[str, list[tuple[CameraProperty, str]]]] = [
    (
        "Разрешение и FPS",
        [
            (CameraProperty.FRAME_WIDTH, "readonly"),
            (CameraProperty.FRAME_HEIGHT, "readonly"),
            (CameraProperty.FPS, "readonly"),
        ],
    ),
    (
        "Экспозиция",
        [
            (CameraProperty.AUTO_EXPOSURE, "checkbox"),
            (CameraProperty.EXPOSURE, "slider"),
            (CameraProperty.GAIN, "slider"),
        ],
    ),
    (
        "Баланс белого",
        [
            (CameraProperty.AUTO_WB, "checkbox"),
            (CameraProperty.WB_TEMPERATURE, "slider"),
        ],
    ),
    (
        "Изображение",
        [
            (CameraProperty.BRIGHTNESS, "slider"),
            (CameraProperty.CONTRAST, "slider"),
            (CameraProperty.SATURATION, "slider"),
            (CameraProperty.HUE, "slider"),
            (CameraProperty.SHARPNESS, "slider"),
            (CameraProperty.GAMMA, "slider"),
            (CameraProperty.BACKLIGHT, "slider"),
        ],
    ),
    (
        "Фокус и зум",
        [
            (CameraProperty.AUTOFOCUS, "checkbox"),
            (CameraProperty.FOCUS, "slider"),
            (CameraProperty.ZOOM, "slider"),
        ],
    ),
]

# Человекочитаемые названия параметров для лейблов.
_LABELS: dict[CameraProperty, str] = {
    CameraProperty.FRAME_WIDTH: "Ширина",
    CameraProperty.FRAME_HEIGHT: "Высота",
    CameraProperty.FPS: "FPS",
    CameraProperty.AUTO_EXPOSURE: "Авто-экспозиция",
    CameraProperty.EXPOSURE: "Экспозиция",
    CameraProperty.GAIN: "Усиление",
    CameraProperty.AUTO_WB: "Авто баланс белого",
    CameraProperty.WB_TEMPERATURE: "Цветовая температура",
    CameraProperty.BRIGHTNESS: "Яркость",
    CameraProperty.CONTRAST: "Контраст",
    CameraProperty.SATURATION: "Насыщенность",
    CameraProperty.HUE: "Оттенок",
    CameraProperty.SHARPNESS: "Резкость",
    CameraProperty.GAMMA: "Гамма",
    CameraProperty.BACKLIGHT: "Компенсация засветки",
    CameraProperty.AUTOFOCUS: "Автофокус",
    CameraProperty.FOCUS: "Фокус",
    CameraProperty.ZOOM: "Зум",
}


class CameraSettingsPanel(QWidget):
    """Панель UVC-параметров камеры: слайдеры, авто-чекбоксы, readonly-лейблы.

    Сигналы:
        property_changed: пользователь сдвинул слайдер или переключил чекбокс.
            Аргументы: (CameraProperty, новое значение float).
    """

    property_changed = pyqtSignal(CameraProperty, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._capture: CaptureThread | None = None
        self._sliders: dict[CameraProperty, QSlider] = {}
        self._spinboxes: dict[CameraProperty, QSpinBox] = {}
        self._reset_buttons: dict[CameraProperty, QPushButton] = {}
        self._checkboxes: dict[CameraProperty, QCheckBox] = {}
        self._readonly_labels: dict[CameraProperty, QLabel] = {}
        # Снапшот первоначальных значений параметров текущей камеры:
        # заполняется при первой интроспекции, используется в Reset-кнопке.
        self._initial_values: dict[CameraProperty, float] = {}
        # Все виджеты, относящиеся к строке параметра (label + контрол + value).
        # При unsupported параметре скрываем все три одновременно.
        self._row_widgets: dict[CameraProperty, list[QWidget]] = {}
        # Группы целиком, чтобы прятать пустые группы при необходимости.
        self._group_boxes: list[QGroupBox] = []
        self._build_layout()
        self._set_controls_enabled(False)

    def set_capture(self, capture: CaptureThread | None) -> None:
        """Привязка к новому CaptureThread или сброс при None.

        При None все контролы дизейблятся. При не-None ждём прихода сигнала
        properties_introspected — он будет обработан слотом
        on_properties_introspected и переинициализирует значения слайдеров.

        Args:
            capture: активный поток захвата или None.
        """
        self._capture = capture
        # Сброс снапшота начальных значений: следующая интроспекция запишет
        # значения новой камеры в _initial_values.
        self._initial_values.clear()
        if capture is None:
            self._set_controls_enabled(False)
            # Видимость групп НЕ сбрасываем: следующая интроспекция плавно
            # подстроит её под новую камеру. Сброс к "все видны" вызывает
            # визуальную вспышку пустых групп между переключениями камер.

    def current_snapshot(self) -> dict[str, float]:
        """Снимок текущих значений активных контролов.

        Контрол считается активным, если он одновременно enabled (т.е. камера
        привязана и параметр поддерживается) и видим на панели.

        Returns:
            dict в формате {CameraProperty.value: float}. Используется в
            RecordingSession.start() для записи в metadata.json.
        """
        snapshot: dict[str, float] = {}
        for prop, slider in self._sliders.items():
            if slider.isEnabled() and slider.isVisibleTo(self):
                snapshot[prop.value] = float(slider.value())
        for prop, checkbox in self._checkboxes.items():
            if checkbox.isEnabled() and checkbox.isVisibleTo(self):
                snapshot[prop.value] = _checkbox_emit_value(prop, checkbox.isChecked())
        return snapshot

    def restore_snapshot(self, snapshot: dict[str, float]) -> None:
        """Восстановление значений контролов из ранее сохранённого снимка.

        Сигналы блокируются на время восстановления, чтобы не сыпать в
        capture десятки property_changed подряд.

        Args:
            snapshot: dict {CameraProperty.value: float}.
        """
        for prop_value, value in snapshot.items():
            try:
                prop = CameraProperty(prop_value)
            except ValueError:
                continue
            slider = self._sliders.get(prop)
            if slider is not None:
                int_value = int(value)
                slider.blockSignals(True)
                slider.setValue(int_value)
                slider.blockSignals(False)
                spinbox = self._spinboxes.get(prop)
                if spinbox is not None:
                    spinbox.blockSignals(True)
                    spinbox.setValue(int_value)
                    spinbox.blockSignals(False)
                continue
            checkbox = self._checkboxes.get(prop)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(_is_auto_value(prop, value))
                checkbox.blockSignals(False)

    @pyqtSlot(dict)
    def on_properties_introspected(self, snapshot: dict[CameraProperty, float]) -> None:
        """Слот для CaptureThread.properties_introspected.

        Скрывает unsupported контролы, выставляет начальные значения
        поддерживаемым слайдерам/чекбоксам, включает редактируемые контролы.

        Обновления интерфейса батчатся через setUpdatesEnabled(False/True),
        чтобы Qt не отрисовывал промежуточные состояния — иначе при
        переключении камер видны вспышки пустых QGroupBox со скруглёнными
        бордерами (выглядят как маленькие диалоговые окна).

        Args:
            snapshot: словарь поддерживаемых параметров и их текущих значений.
        """
        self.setUpdatesEnabled(False)
        try:
            for prop, widgets in self._row_widgets.items():
                visible = prop in snapshot
                for w in widgets:
                    w.setVisible(visible)
            for prop, value in snapshot.items():
                self._apply_introspected_value(prop, value)
            # Скрыть пустые группы целиком (если все строки группы скрыты)
            self._collapse_empty_groups()
            # Включить редактируемые контролы (slider/checkbox), readonly — нет смысла
            self._set_controls_enabled(True)
        finally:
            self.setUpdatesEnabled(True)

    def _apply_introspected_value(self, prop: CameraProperty, value: float) -> None:
        """Установка значения в конкретный контрол по результатам интроспекции.

        Снапшот начальных значений (для Reset-кнопки) заполняется только при
        ПЕРВОЙ интроспекции для каждой камеры — set_capture() сбрасывает
        _initial_values, после чего здесь происходит первое заполнение.
        """
        readonly = self._readonly_labels.get(prop)
        if readonly is not None:
            readonly.setText(str(int(value)) if value.is_integer() else f"{value:.2f}")
            return
        slider = self._sliders.get(prop)
        if slider is not None:
            slider_min = slider.minimum()
            slider_max = slider.maximum()
            clamped = max(slider_min, min(slider_max, int(value)))
            if prop not in self._initial_values:
                self._initial_values[prop] = float(clamped)
            slider.blockSignals(True)
            slider.setValue(clamped)
            slider.blockSignals(False)
            spinbox = self._spinboxes.get(prop)
            if spinbox is not None:
                spinbox.blockSignals(True)
                spinbox.setValue(clamped)
                spinbox.blockSignals(False)
            return
        checkbox = self._checkboxes.get(prop)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(_is_auto_value(prop, value))
            checkbox.blockSignals(False)

    def _build_layout(self) -> None:
        """Сборка scroll area + групп с контролами."""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(8)
        inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for title, items in _GROUPS:
            group = self._build_group(title, items)
            self._group_boxes.append(group)
            inner_layout.addWidget(group)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    def _build_group(self, title: str, items: list[tuple[CameraProperty, str]]) -> QGroupBox:
        """Сборка одной QGroupBox с набором строк-контролов."""
        group = QGroupBox(title)
        group.setStyleSheet(f"QGroupBox {{ font-family: {FONT_UI}; font-weight: 600; }}")
        grid = QGridLayout()
        grid.setContentsMargins(8, 12, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        for row_idx, (prop, kind) in enumerate(items):
            self._row_widgets[prop] = self._build_row(prop, kind, grid, row_idx)

        group.setLayout(grid)
        return group

    def _build_row(
        self,
        prop: CameraProperty,
        kind: str,
        grid: QGridLayout,
        row_idx: int,
    ) -> list[QWidget]:
        """Сборка одной строки grid и возврат списка её виджетов.

        Возвращённый список используется для одновременного setVisible() всех
        ячеек строки (label + контрол + value-label при наличии).
        """
        name_label = QLabel(_LABELS.get(prop, prop.value))
        grid.addWidget(name_label, row_idx, 0)
        row: list[QWidget] = [name_label]

        if kind == "slider":
            slider = QSlider(Qt.Orientation.Horizontal)
            rng = property_range(prop) or _FALLBACK_SLIDER_RANGE
            slider.setRange(rng[0], rng[1])
            slider.setValue(rng[0])
            slider.setMinimumWidth(_SLIDER_MIN_WIDTH)
            spinbox = QSpinBox()
            spinbox.setRange(rng[0], rng[1])
            spinbox.setValue(rng[0])
            spinbox.setMaximumWidth(_SPINBOX_MAX_WIDTH)
            reset_button = QPushButton(_RESET_BUTTON_TEXT)
            reset_button.setMinimumWidth(_RESET_BUTTON_MIN_WIDTH)
            reset_button.setMaximumWidth(_RESET_BUTTON_MAX_WIDTH)
            reset_button.setToolTip("Сбросить к начальному значению камеры")
            grid.addWidget(slider, row_idx, 1)
            grid.addWidget(spinbox, row_idx, 2)
            grid.addWidget(reset_button, row_idx, 3)
            self._sliders[prop] = slider
            self._spinboxes[prop] = spinbox
            self._reset_buttons[prop] = reset_button
            slider.valueChanged.connect(lambda v, p=prop: self._on_slider_changed(p, v))
            spinbox.valueChanged.connect(lambda v, p=prop: self._on_spinbox_changed(p, v))
            reset_button.clicked.connect(lambda _checked=False, p=prop: self._on_reset_clicked(p))
            row.extend([slider, spinbox, reset_button])
        elif kind == "checkbox":
            checkbox = QCheckBox()
            grid.addWidget(checkbox, row_idx, 1, 1, 3)
            self._checkboxes[prop] = checkbox
            checkbox.toggled.connect(lambda on, p=prop: self._on_checkbox_toggled(p, on))
            row.append(checkbox)
        elif kind == "readonly":
            readonly = QLabel("—")
            readonly.setStyleSheet(f"color: {TEXT_MUTED};")
            grid.addWidget(readonly, row_idx, 1, 1, 3)
            self._readonly_labels[prop] = readonly
            row.append(readonly)
        else:
            raise ValueError(f"Неизвестный kind '{kind}' для {prop.value}")

        return row

    def _on_slider_changed(self, prop: CameraProperty, value: int) -> None:
        """Обработка движения слайдера: синхронизация спинбокса + эмит сигнала.

        Спинбокс синхронизируется с заблокированными сигналами, чтобы не
        вернуть управление обратно в slider через _on_spinbox_changed.
        """
        spinbox = self._spinboxes.get(prop)
        if spinbox is not None and spinbox.value() != value:
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.blockSignals(False)
        self.property_changed.emit(prop, float(value))

    def _on_spinbox_changed(self, prop: CameraProperty, value: int) -> None:
        """Обработка ручного ввода в спинбокс: проброс в slider.

        Слайдер обновляется через setValue без блокировки сигналов — он сам
        вызовет _on_slider_changed (если значение фактически изменилось), что
        приведёт к единственному эмиту property_changed. Если значения уже
        совпадают, ничего не делаем, чтобы избежать инфинит-лупа.
        """
        slider = self._sliders.get(prop)
        if slider is None:
            return
        if slider.value() == value:
            return
        slider.setValue(value)

    def _on_reset_clicked(self, prop: CameraProperty) -> None:
        """Сброс значения слайдера: initial-снапшот текущей камеры или дефолт.

        Initial-значение приоритетнее: оно записано при первой интроспекции
        текущей камеры. Если по какой-то причине отсутствует — fallback на
        property_default(). Если и его нет — ничего не делаем.
        """
        target = self._initial_values.get(prop)
        if target is None:
            target = property_default(prop)
        if target is None:
            return
        slider = self._sliders.get(prop)
        if slider is None:
            return
        slider_min = slider.minimum()
        slider_max = slider.maximum()
        clamped = max(slider_min, min(slider_max, int(target)))
        slider.setValue(clamped)

    def _on_checkbox_toggled(self, prop: CameraProperty, on: bool) -> None:
        """Обработка переключения чекбокса AUTO_*: эмит платформозависимого value."""
        self.property_changed.emit(prop, _checkbox_emit_value(prop, on))

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Массовое включение/выключение редактируемых контролов."""
        for slider in self._sliders.values():
            slider.setEnabled(enabled)
        for spinbox in self._spinboxes.values():
            spinbox.setEnabled(enabled)
        for reset_button in self._reset_buttons.values():
            reset_button.setEnabled(enabled)
        for checkbox in self._checkboxes.values():
            checkbox.setEnabled(enabled)

    def _reset_visibility_all_visible(self) -> None:
        """Возврат всех строк и групп в видимое состояние (для сброса)."""
        for widgets in self._row_widgets.values():
            for w in widgets:
                w.setVisible(True)
        for group in self._group_boxes:
            group.setVisible(True)

    def _collapse_empty_groups(self) -> None:
        """Скрытие групп, в которых не осталось видимых строк."""
        for group in self._group_boxes:
            layout = group.layout()
            if layout is None:
                continue
            any_visible = False
            for i in range(layout.count()):
                item = layout.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is not None and widget.isVisible():
                    any_visible = True
                    break
            group.setVisible(any_visible)
