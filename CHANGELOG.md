# Changelog

Все значимые изменения в проекте документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект использует [Semantic Versioning](https://semver.org/lang/ru/).

## [1.0.0] — 2026-05-25

Первый стабильный релиз. Готов к использованию научными коллегами для записи
видео и кадров с UVC-камер на Linux, macOS и Windows.

### Захват и камера

- Платформо-зависимый поиск камер: `/dev/video*` через `glob` на Linux,
  scan-by-index с early-exit на macOS / Windows / fallback.
- `CaptureThread` (`QThread`) с thread-safe очередью применения UVC-параметров
  между кадрами.
- Live preview через `QImage` / `QPixmap` с масштабированием под виджет.
- Интроспекция поддерживаемых UVC-параметров через `cap.get()` после открытия.
- Верификация применения параметров через обратное чтение `cap.get()` после
  `cap.set()` — warning в лог, если параметр не применился (типично для
  macOS AVFoundation на встроенных камерах).

### Запись

- Параллельный pipeline: видео + отдельные кадры из одного источника.
- `VideoWriterThread` с цепочками fallback по контейнерам:
  - H.264 (`avc1`) → MP4V → MJPG (всё в `.mp4`)
  - VP9 → VP8 (`.webm`)
  - MJPG → только MJPG (`.avi`)
- Lazy-init `VideoWriter` на первом кадре с реальными dimensions камеры
  (cap может вернуть не запрошенный размер).
- `FrameSaverPool` (PNG / JPG / BMP) на `ThreadPoolExecutor` с backpressure-
  дропом при переполнении.
- Frame throttling: `target_fps` ниже скорости камеры — лишние кадры
  пропускаются, file-size масштабируется линейно.
- Поддержка дробного fps вплоть до `0.1` (time-lapse режим).
- Защита от C++ exception в кодеке (особенно `avc1` при fps < 1.0): зажим
  до минимума 1.0 для writer, throttle обрабатывается отдельно.
- Auto-abort сессии при провале VideoWriter с удалением частичных артефактов
  (не остаётся папки только с PNG без видео).
- `metadata.json` per session: target/actual fps, dimensions, codec, snapshot
  UVC-параметров на момент старта, число дропов.

### UI

- `MainWindow`: топбар (камера + папка) + центральный preview + правая UVC-
  панель + recording controls + status bar.
- Скрываемая UVC-панель через `QSplitter` с drag-handle и persistent
  состоянием (visibility + sizes сохраняются в QSettings).
- 19 UVC-слайдеров (brightness / contrast / saturation / hue / sharpness /
  gamma / backlight / exposure / gain / WB temperature / focus / zoom + auto-
  чекбоксы + readonly resolution/fps) с per-property диапазонами и кнопками
  "Сброс" к initial-значению.
- Platform-correct auto-toggle значения для `AUTO_EXPOSURE` (Linux V4L2: 1/3,
  остальные: 0/1).
- Toggle-кнопка REC/Stop с red/slate состояниями.
- Settings dialog: папка записей (с QFileDialog), формат фреймов с динамической
  подписью качества (PNG compression / JPG quality / BMP скрыт), кодек видео
  (H.264 / MP4V / MJPG / VP9-WebM), float FPS-поле без стрелок с C-локалью
  (точка как разделитель), hotkey через `QKeySequenceEdit`, таймер автостопа.
- Hotkey `Ctrl+R` (настраиваемый) для toggle записи.
- Таймер автостопа с прерыванием по достижении.

### Infrastructure

- Cross-platform логирование:
  - Linux: `~/.local/share/plasma-dog/log.txt`
  - macOS: `~/Library/Logs/plasma-dog/log.txt`
  - Windows: `%APPDATA%\plasma-dog\log.txt`
- Rotating log handler (5 MB × 3 файла).
- `QSettings` для персистентных настроек: папка, формат, кодек, fps, hotkey,
  snapshot слайдеров, последняя камера, состояние splitter.
- Проверка свободного места перед стартом записи (< 100 MB — abort, < 500 MB —
  warning).

### Стек

- Python 3.13 + uv
- PyQt6 ≥ 6.7
- opencv-python ≥ 4.10
- numpy ≥ 2.0
- dev: ruff, black, mypy (strict), pytest, pytest-qt

### Документация

- README.md с инструкциями установки на Linux / macOS / Windows (winget,
  Chocolatey, ручная установка), доступ к камере, запуск в Docker, автозапуск
  через systemd / LaunchAgent / Task Scheduler.
- `docs/architecture.md` с Mermaid-диаграммами data flow / threading /
  модулей.
- 74 теста (lint + typecheck + pytest).

### Известные ограничения

- На macOS встроенные FaceTime-камеры через AVFoundation backend OpenCV
  игнорируют большинство `cap.set()` для UVC-параметров. Слайдеры читаются,
  но не применяются. Внешние USB UVC-камеры работают.
- VP9 / WebM на macOS недоступен (opencv-python wheel не включает libvpx).
  Fallback по цепочке внутри `.webm` контейнера: VP9 → VP8 → abort. Без падения
  процесса, ошибка показывается в UI.
- Docker-контейнер с GUI работает только на Linux-хосте (X11 forwarding +
  `--device /dev/video0`). На macOS / Windows нужен native запуск.

### Лицензия

Apache License 2.0.

[1.0.0]: https://github.com/kskadart/plasma-dog/releases/tag/v1.0.0
