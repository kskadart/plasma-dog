# plasma-dog

Desktop-приложение для синхронной записи видео и отдельных кадров плазмы горения с USB UVC-камеры. Целевая аудитория — лабораторные операторы научных экспериментов, которым нужно одновременно получить непрерывный видеопоток для общего обзора и набор PNG-кадров для последующего покадрового анализа.

Все ключевые параметры камеры (exposure, gain, white balance, brightness, contrast, saturation, sharpness, gamma, focus) выведены в боковую панель и применяются на лету. Запись запускается кнопкой, hotkey'ом или по таймеру с автостопом.

## Возможности

- Параллельная запись H.264 видео и отдельных PNG/JPG/BMP-фреймов в реальном времени.
- Live превью камеры до начала записи и во время.
- Поддержка любой UVC-камеры на Windows, Linux и macOS (бэкенды DirectShow, V4L2, AVFoundation).
- Полный набор UVC-слайдеров с автоматическим скрытием неподдерживаемых параметров.
- Hotkey старт/стоп (по умолчанию `Ctrl+R`) и таймер автостопа.
- Сохранение пользовательских настроек между запусками: папка записей, формат фреймов, последние значения слайдеров, выбранная камера.
- Backpressure: при отставании диска кадры дропаются вместо рассинхрона; число дропов попадает в лог и `metadata.json`.
- Запись `metadata.json` с фактическим fps и snapshot всех UVC-параметров для воспроизводимости эксперимента.

## Поддерживаемые форматы

### Видео-кодеки

Выбираются в `Файл → Настройки... → Кодек видео`. По умолчанию H.264. При провале первичного кодека приложение пробует fallback по цепочке внутри того же контейнера (без миксования mp4/webm/avi).

| Кодек | FOURCC | Контейнер | Сжатие | Цепочка fallback | Платформы | Когда выбирать |
|---|---|---|---|---|---|---|
| **H.264** (default) | `avc1` | `.mp4` | Lossy, эффективное | `avc1 → mp4v → MJPG` (всё в `.mp4`) | Linux, macOS, Windows | По умолчанию: лучший баланс размер/качество, открывается везде |
| **MP4V** | `mp4v` | `.mp4` | Lossy, среднее | `mp4v → avc1 → MJPG` (всё в `.mp4`) | Linux, Windows; **на macOS не открывается** (fallback на avc1) | Старый legacy-плеер, не поддерживающий H.264 |
| **MJPG** | `MJPG` | `.avi` | Per-frame JPEG, без межкадрового | только `MJPG` | Linux, macOS, Windows | Простой формат, лёгкое покадровое извлечение, **большой файл (~10× H.264)**, нет inter-frame артефактов |
| **VP9 / WebM** | `VP90` | `.webm` | Lossy, отличное | `VP90 → VP80` (только WebM) | Linux (FFmpeg с libvpx); **на macOS Windows opencv-python wheel может не содержать VP** | Open-стандарт, веб-просмотр без перекодирования. На macOS обычно не работает — fallback внутри `.webm` невозможен → сессия отменяется. |

**Защита от мисматча контейнер/кодек**: цепочки fallback ограничены кодеками, совместимыми с расширением файла. Нельзя писать `mp4v` в `.webm` — это даёт битый файл. Если внутри контейнера ни один кодек не открылся, `RecordingSession` отменяет запись с удалением частичных артефактов (не остаётся папки только с PNG без видео).

**Sub-1 fps (time-lapse)**: writer fps зажимается снизу до 1.0 (H.264 кидает `cv2.error` на fps < 1). Throttling в `RecordingSession` режет кадры под пользовательский target_fps. При target=0.5 за 10 секунд реального времени записывается 5 уникальных кадров, видео-контейнер содержит fps=1.0 → playback ускорен 2× (классический time-lapse).

### Форматы отдельных кадров

Выбираются в `Файл → Настройки... → Формат фреймов`. Кадры пишутся параллельно с видео в `frames/000001.png` (инкрементная нумерация).

| Формат | Расширение | Сжатие | Параметр качества | Размер (1080p) | Когда выбирать |
|---|---|---|---|---|---|
| **PNG** (default) | `.png` | Lossless | Compression level 0..9 (0 — без сжатия, 9 — макс) | ~2-5 MB на кадр | Научный анализ: без потерь, можно открыть в любом ПО, безопасно для долгого хранения. Compression level не влияет на качество, только на CPU/размер. |
| **JPG** | `.jpg` | Lossy | Quality 1..100 (100 — макс качество) | ~200-500 KB на кадр | Большие сессии где экономия места критичнее микро-артефактов. При quality=95 артефакты практически незаметны. |
| **BMP** | `.bmp` | Без сжатия | (не применяется) | ~6 MB на кадр | Совместимость с устаревшим ПО, отсутствие любых артефактов. Самый большой размер. |

**Backpressure**: при отставании диска (typical bottleneck для PNG @ 30 fps @ 1080p) `FrameSaverPool` дропает кадры вместо рассинхрона с записью видео. Число дропов попадает в `metadata.json` и в status bar.

## Требования

- Python 3.13+
- USB UVC-совместимая камера
- ОС: Linux, macOS или Windows
- Пакетный менеджер `uv` (https://docs.astral.sh/uv/)

## Установка по платформам

### Linux (Ubuntu / Debian / Fedora)

```bash
# 1. Python 3.13+ и системные библиотеки для Qt6 / OpenCV / V4L2
sudo apt update
sudo apt install -y \
    python3 python3-pip git build-essential ca-certificates curl \
    libgl1 libglib2.0-0 \
    libxkbcommon0 libxkbcommon-x11-0 \
    libfontconfig1 libfreetype6 \
    libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 \
    libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 \
    libdbus-1-3 libxext6 libxrender1 libsm6 libice6 \
    ffmpeg v4l-utils

# Fedora / RHEL / AlmaLinux:
# sudo dnf install -y python3 git gcc gcc-c++ make ca-certificates curl \
#     mesa-libGL glib2 \
#     libxkbcommon libxkbcommon-x11 \
#     fontconfig freetype \
#     libxcb xcb-util-cursor xcb-util-image xcb-util-keysyms \
#     xcb-util-renderutil xcb-util-wm xcb-util \
#     dbus-libs libXext libXrender libSM libICE \
#     ffmpeg v4l-utils

# Arch / Manjaro:
# sudo pacman -S --needed python git base-devel \
#     mesa libglvnd libxkbcommon libxkbcommon-x11 \
#     xcb-util-cursor xcb-util-image xcb-util-keysyms \
#     xcb-util-renderutil xcb-util-wm \
#     fontconfig freetype2 dbus \
#     ffmpeg v4l-utils

# 2. uv (быстрый менеджер зависимостей)
curl -LsSf https://astral.sh/uv/install.sh | sh
# либо: pip install --user uv

# 3. Доступ к /dev/video*
sudo usermod -aG video $USER   # перелогинься после этой команды

# 4. Проект
git clone <repo-url> plasma-dog
cd plasma-dog
make install
```

**Системные зависимости — зачем:**
- `libgl1`, `libglib2.0-0` — OpenGL + GLib для Qt6/OpenCV
- `libxcb-*`, `libxkbcommon*`, `libfontconfig1` — Qt6 platform plugin для X11/Wayland
- `libdbus-1-3` — IPC для Qt
- `ffmpeg`, `v4l-utils` — диагностика камеры + альтернативный backend для OpenCV кодеков

### macOS

```bash
# 1. Xcode Command Line Tools (если ещё нет)
xcode-select --install

# 2. Homebrew (если ещё нет)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 3. Python 3.13 + uv + git
brew install python@3.13 uv git

# 4. Проект
git clone <repo-url> plasma-dog
cd plasma-dog
make install
```

**Зависимости macOS:**
- Все библиотеки Qt6 / OpenCV приходят внутри Python wheels (PyQt6, opencv-python) — отдельная установка не нужна.
- При первом запуске macOS попросит разрешение на доступ к камере: `System Settings → Privacy & Security → Camera` → разреши Terminal / iTerm (или приложение, из которого запускаешь `make run`).
- Сброс прав камеры (если попал в "Don't Allow"): `tccutil reset Camera`.

### Windows 10 / 11

Три способа на выбор: **winget** (встроен в Win 10 1709+ и Win 11), **Chocolatey**, или **ручная установка** официальными installer'ами. Команду `make` на Windows ставить опционально — `uv` справляется без него.

Проверь, есть ли уже winget: в PowerShell — `winget --version`. Если выдаёт версию — используй вариант 1.

#### Вариант 1: winget (рекомендуется)

```powershell
# 1. Python 3.13, uv, git
winget install Python.Python.3.13
winget install astral-sh.uv
winget install Git.Git

# 2. Перезапусти PowerShell чтобы PATH обновился.

# 3. Visual C++ Redistributable (нужен для PyQt6 и opencv-python).
#    Обычно уже установлен на Win10/11, если нет:
# winget install Microsoft.VCRedist.2015+.x64

# 4. Проект
git clone <repo-url> plasma-dog
cd plasma-dog
uv sync
uv run plasma-dog
```

#### Вариант 2: Chocolatey

Установи [Chocolatey](https://chocolatey.org/install) (одноразовый PowerShell-скрипт от админа), затем:

```powershell
choco install python --version=3.13.0 -y
choco install uv -y
choco install git -y
# Опционально: choco install make -y  (если хочется Makefile-команды)

# Перезапусти PowerShell

git clone <repo-url> plasma-dog
cd plasma-dog
uv sync
uv run plasma-dog
```

#### Вариант 3: Ручная установка (без пакетного менеджера)

Подходит, если winget недоступен (Windows Server, корпоративная блокировка Store) и не хочется ставить Chocolatey.

1. **Python 3.13**: скачай с [python.org/downloads/windows](https://www.python.org/downloads/windows/) — выбери "Windows installer (64-bit)". В installer'е **обязательно поставь галочку "Add python.exe to PATH"** перед нажатием Install.

   Проверить: в PowerShell `python --version` → должен выдать `Python 3.13.x`.

2. **Git for Windows**: скачай с [git-scm.com/download/win](https://git-scm.com/download/win), запусти installer (все галочки по умолчанию подходят).

   Проверить: `git --version`.

3. **uv**: один из вариантов, выбери удобный:

   **3a. Через pip** (Python 3.13 уже стоит):
   ```powershell
   pip install --user uv
   ```

   **3b. Через официальный PowerShell-скрипт** (Microsoft Defender может предупредить про executable from internet):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Проверить: открой новый PowerShell → `uv --version`.

4. **Visual C++ Redistributable** (нужен для PyQt6 и opencv-python). Обычно уже установлен на Win10/11 — проверь в `Settings → Apps → Installed apps`, найди "Microsoft Visual C++ 2015-2022 Redistributable (x64)". Если нет:

   - Скачай с [aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe), запусти installer.

5. **Проект**:
   ```powershell
   git clone <repo-url> plasma-dog
   cd plasma-dog
   uv sync
   uv run plasma-dog
   ```

#### Зависимости Windows — что включено в wheels

- **PyQt6, opencv-python** — wheels со всеми Qt6 и OpenCV DLL внутри. Отдельная установка Qt / OpenCV **не нужна**.
- **Visual C++ Runtime** (`VCRUNTIME140.dll`, `MSVCP140.dll`) — должен быть в системе (пункт 4 выше).
- **H.264 кодек** для записи `avc1`: на Windows 10/11 идёт в составе системы. Если `avc1` не открывается на конкретной машине — приложение автоматически делает fallback на `mp4v` → `MJPG`. Можно явно выбрать кодек в Настройках (`Файл → Настройки... → Кодек видео`).

## Запуск

| Платформа | Команда                          |
|-----------|----------------------------------|
| Linux     | `make run` или `uv run plasma-dog` |
| macOS     | `make run` или `uv run plasma-dog` |
| Windows   | `uv run plasma-dog`                |

Через python-модуль (на любой ОС):

```
uv run python -m plasma_dog
```

## Доступ к камере по платформам

### Linux

- Камера должна быть видна как `/dev/video0`, `/dev/video1` и так далее.
- Пользователь должен входить в группу `video`: `sudo usermod -aG video $USER`, затем перелогиниться.
- Проверь устройства: `ls /dev/video*` и `v4l2-ctl --list-devices` (если установлен пакет `v4l-utils`).
- Бэкенд OpenCV: V4L2 (поддерживает большинство UVC-настроек через `cap.set()`).

### macOS

- macOS блокирует доступ к камере через TCC (Transparency, Consent, and Control).
- Первый запуск из терминала вызовет диалог "Terminal хочет доступ к камере". Если случайно нажал "Don't Allow", разрешение даётся в `System Settings → Privacy & Security → Camera`.
- Сброс прав (если нужно перезапросить): `tccutil reset Camera`.
- Бэкенд OpenCV: AVFoundation. **Ограничения**: большинство UVC-параметров (brightness, exposure, WB и т.д.) **игнорируются на встроенных FaceTime камерах** — слайдеры доступны в UI, но `cap.set()` возвращает `False`, в логе появляется warning. На внешних USB UVC-камерах работает.

### Windows

- Включи доступ к камере: `Settings → Privacy & security → Camera` → "Camera access" и "Let apps access your camera" должны быть включены, плюс разреши конкретно для desktop-приложений.
- Бэкенд OpenCV: DirectShow (поддерживает UVC-настройки).
- Если камера не видна — проверь Device Manager на наличие "Imaging devices" / "Cameras".

## Запуск в Docker

В репозитории лежат `Dockerfile` + `docker-compose.yml`. **Docker реально работает только на Linux-хосте**: USB-камеру нужно прокинуть в контейнер через `--device /dev/video0`, а GUI — через X11 socket. На macOS и Windows Docker крутится в Linux-VM, проброс USB-камеры туда требует `usbipd-win` или аналогов, и нативный запуск гораздо проще.

### Linux: build + run

```bash
# 1. Собрать образ
docker compose build
# либо: docker build -t plasma-dog:local .

# 2. Разрешить X11 локальным docker-контейнерам (на одну сессию)
xhost +local:docker

# 3. Запуск
docker compose up
# либо вручную:
# docker run --rm -it \
#   --network host \
#   --device /dev/video0 \
#   --group-add video \
#   -e DISPLAY=$DISPLAY \
#   -e QT_X11_NO_MITSHM=1 \
#   -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
#   -v $HOME/recordings/plasma-dog:/root/recordings/plasma-dog \
#   plasma-dog:local
```

После остановки откати X11-доступ: `xhost -local:docker`.

### macOS / Windows: предупреждение

Docker Desktop на macOS/Windows запускает Linux-VM. USB-камера хоста **не видна** контейнеру по умолчанию:

- **Windows**: нужен [usbipd-win](https://github.com/dorssel/usbipd-win) для проброса USB → WSL2 → Docker. Сложно и нестабильно.
- **macOS**: нет официального решения для USB-passthrough в Docker Desktop. Только сторонние решения (VirtualHere, network-attached USB).

**Рекомендация для macOS/Windows: запускать нативно через `uv run plasma-dog`** — Python + Qt6 + OpenCV отлично работают вне контейнера.

### Что внутри Dockerfile

- База: `python:3.13-slim-bookworm`.
- Системные пакеты: Qt6 X11 deps, OpenGL, V4L2, ffmpeg, v4l-utils.
- `uv sync --frozen --no-dev` — production deps без dev-инструментов.
- Volume `/data/recordings` для записей.

### Что НЕ покрыто Docker

- Hotkey глобальные клавиши (контейнер изолирован от input системы хоста).
- Автозапуск Settings-диалога с native open-file picker — может вести себя странно через X11.
- Settings (`QSettings`) пишутся внутри контейнера, не персистятся между запусками если не смонтировать volume. Для постоянного хранения добавь в `docker-compose.yml`:
  ```yaml
  - ${HOME}/.config/plasma-dog:/root/.config/plasma-dog:rw
  ```

## Запуск в фоновом / автоматическом режиме

Приложение — это GUI с превью; для постоянного фонового использования настрой автозапуск пользовательской сессии.

### Linux (systemd user service)

`~/.config/systemd/user/plasma-dog.service`:

```ini
[Unit]
Description=plasma-dog recording app
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/plasma-dog
ExecStart=%h/.local/bin/uv run plasma-dog
Restart=on-failure

[Install]
WantedBy=default.target
```

Активация:

```bash
systemctl --user daemon-reload
systemctl --user enable --now plasma-dog.service
```

GUI требует активный X11/Wayland — при логине пользователя сервис стартует автоматически.

### macOS (LaunchAgent)

`~/Library/LaunchAgents/com.plasma-dog.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.plasma-dog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/uv</string>
        <string>run</string>
        <string>--project</string>
        <string>/Users/USERNAME/plasma-dog</string>
        <string>plasma-dog</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><false/>
</dict>
</plist>
```

Загрузка: `launchctl load ~/Library/LaunchAgents/com.plasma-dog.plist`.

### Windows (Task Scheduler)

1. Открой `Task Scheduler` (`taskschd.msc`).
2. `Create Basic Task` → имя `plasma-dog`.
3. Trigger: `When I log on`.
4. Action: `Start a program`:
   - Program/script: `uv.exe` (полный путь, например `C:\Users\USERNAME\.local\bin\uv.exe`)
   - Arguments: `run plasma-dog`
   - Start in: `C:\Users\USERNAME\plasma-dog`
5. Finish → задача появится в `Task Scheduler Library`.

Альтернатива — добавить ярлык в папку автозагрузки: `Win + R` → `shell:startup` → создать `.bat`-файл:

```bat
@echo off
cd /d C:\Users\USERNAME\plasma-dog
uv run plasma-dog
```

## Использование

1. Запустите приложение. В верхней части окна выберите камеру из списка (кнопка `Обновить` пересканирует устройства).
2. Дождитесь, пока появится live превью и боковая панель заполнится поддерживаемыми UVC-параметрами.
3. Откорректируйте параметры (exposure, gain, WB и т.д.) — изменения видны на превью сразу.
4. Откройте `Файл -> Настройки...` (`Ctrl+,`), чтобы выбрать корневую папку записей, формат фреймов и hotkey.
5. Нажмите кнопку `REC` (или нажмите hotkey) для начала записи. Для автостопа через N секунд установите значение таймера и нажмите `REC с таймером`.
6. Кнопка `Stop` (или повторное нажатие hotkey) корректно завершит запись, дозапишет буферы и сохранит `metadata.json`.

## Структура папки записи

Каждая сессия — отдельная папка с timestamp-именем:

```
recordings/
  2026-05-25_14-30-00/
    video.mp4          H.264 непрерывная запись
    frames/
      000001.png       инкрементные кадры
      000002.png
      ...
    metadata.json      fps, разрешение, кодек, длительность, UVC-параметры
```

`metadata.json` содержит:

- `started_at` / `stopped_at` — границы записи
- `camera_index`, `width`, `height`, `target_fps`, `fourcc`
- `frames_written`, `frames_dropped`, `actual_fps` — фактическая статистика
- `camera_properties` — snapshot всех UVC-значений на момент старта

## Архитектура

Подробно: [docs/architecture.md](docs/architecture.md).

Кратко: один `CaptureThread` читает кадры с камеры, эмитит сигнал `frame_ready` на три потребителя — preview-виджет, `VideoWriterThread` (cv2.VideoWriter), `FrameSaverPool` (ThreadPoolExecutor для параллельной PNG-компрессии). При переполнении очередей кадры дропаются — это спасает realtime, но фиксируется в логах и метаданных.

## Разработка

Доступные команды Makefile:

| Цель        | Что делает                                |
|-------------|-------------------------------------------|
| `install`   | `uv sync`                                 |
| `lint`      | `ruff check`                              |
| `format`    | `black` + `ruff check --fix`              |
| `typecheck` | `mypy --strict`                           |
| `tests`     | `pytest`                                  |
| `run`       | Запуск приложения                         |
| `all`       | `format` + `lint` + `typecheck` + `tests` |
| `clean`     | Удалить кеши и build-артефакты            |

Перед коммитом запускайте `make all`.

## Логи

Приложение пишет логи одновременно в stderr и в ротируемый файл (5 MB, 3 архива). Путь к файлу выводится в первой INFO-строке при старте.

| ОС      | Путь                                       |
|---------|--------------------------------------------|
| Linux   | `~/.local/share/plasma-dog/log.txt` (или `$XDG_DATA_HOME/plasma-dog/log.txt`) |
| macOS   | `~/Library/Logs/plasma-dog/log.txt`        |
| Windows | `%APPDATA%\plasma-dog\log.txt`             |

## Persistence пользовательских настроек

Используется нативный `QSettings`. Расположение:

| ОС      | Путь                                                       |
|---------|------------------------------------------------------------|
| Linux   | `~/.config/plasma-dog/plasma-dog.conf`                     |
| macOS   | `~/Library/Preferences/com.plasma-dog.plasma-dog.plist`    |
| Windows | `HKEY_CURRENT_USER\Software\plasma-dog\plasma-dog`         |

## Лицензия

[Apache License 2.0](LICENSE) — permissive лицензия с patent grant. Используется в TensorFlow, Kubernetes и большинстве научных open-source проектов. Можно использовать в коммерческих продуктах и форках, обязательно сохранение copyright/notice при распространении.
