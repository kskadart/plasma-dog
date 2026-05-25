# plasma-eye Docker image.
#
# Назначение:
#  - CI/build verification на чистом Linux окружении.
#  - Запуск на Linux-хосте с X11 forwarding и проброшенной /dev/video* камерой
#    (см. docker-compose.yml и инструкцию в README).
#
# Ограничения:
#  - macOS/Windows: Docker крутится в Linux-VM. Проброс USB-камеры в VM
#    требует отдельной настройки (usbipd-win / VirtualHere); проще запустить
#    приложение нативно через `uv run plasma-eye`.
#  - X11: контейнер ожидает доступный X-сервер на хосте. Wayland — через XWayland.

FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Системные зависимости для Qt6, OpenCV (видео + V4L2) и UVC-камер.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
        libgl1 libglib2.0-0 \
        libxkbcommon0 libxkbcommon-x11-0 \
        libfontconfig1 libfreetype6 \
        libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 \
        libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 \
        libdbus-1-3 libxext6 libxrender1 libsm6 libice6 \
        ffmpeg v4l-utils \
 && rm -rf /var/lib/apt/lists/*

# uv (быстрый менеджер зависимостей)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && cp /root/.local/bin/uv /usr/local/bin/uv \
 && uv --version

WORKDIR /app

# Слой кеша зависимостей: сначала только lock + manifest.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Исходники + установка самого проекта
COPY src ./src
COPY tests ./tests
COPY Makefile ./
RUN uv sync --frozen --no-dev

# Папка для артефактов записи (mount-point для docker-compose volume)
VOLUME ["/data/recordings"]

# Запуск GUI приложения. Требует DISPLAY и подключённую камеру.
CMD ["uv", "run", "plasma-eye"]
