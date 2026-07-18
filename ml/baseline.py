"""Baseline-классификатор «плохо/хорошо» с честной оценкой протоколов.

Метка класса — в имени сессии: плохо=1 (детектируемый класс), хорошо=0.

Данные имеют жёсткие ограничения (см. ml/README.md): всего 3 записи, из них
одна класса 0; кадры внутри сессии — почти-дубликаты (corr соседних ~0.999,
эффективная размерность ~1.2). Поэтому скрипт СПЕЦИАЛЬНО сравнивает три
протокола оценки на одних и тех же данных:

  A. Random 80/20  — НЕЧЕСТНЫЙ (утечка через почти-дубликаты). Для контраста.
  B. Temporal per-session holdout — train=начало сессии, test=хвост, с разрывом.
  C. Leave-one-session-out (LOSO) — единственный протокол, проверяющий перенос
     на ДРУГУЮ запись. Класс 0 держать в test нельзя (сессия одна) — это явно
     отражается в выводе.

Дополнительно — «проба конфаундинга»: логрегрессия только на 2 глобальных
признаках (яркость V, насыщенность S). Если она уже даёт ~100%, значит классы
разделяются тривиальной глобальной статистикой, а не структурой плазмы.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = "data/raw/Снимки и видео"
CACHE = "data/eda/features.npz"
LABELS = {"плохо": 1, "хорошо": 0}
CONTENT_RES = 24  # сторона нормализованного content-патча
SEED = 0


def session_label(name: str) -> int:
    """Метка класса из последнего слова имени сессии."""
    return LABELS[name.strip().split()[-1].lower()]


def _frame_features(path: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Глобальные (8) и content-признаки (CONTENT_RES^2) одного кадра.

    Global: mean/std V, mean/std S, mean B, G, R — прокси настроек камеры/сцены.
    Content: grayscale -> CLAHE -> resize -> per-frame z-норма (убирает глобальную
    яркость, оставляет пространственную структуру).
    """
    color = cv2.imread(path, cv2.IMREAD_REDUCED_COLOR_4)
    if color is None:
        return None
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    v = hsv[:, :, 2].astype(np.float32)
    glob = np.array(
        [
            v.mean(), v.std(), s.mean(), s.std(),
            color[:, :, 0].mean(), color[:, :, 1].mean(), color[:, :, 2].mean(),
            float(cv2.Laplacian(v, cv2.CV_32F).var()),  # резкость/структура
        ],
        dtype=np.float32,
    )

    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    patch = cv2.resize(gray, (CONTENT_RES, CONTENT_RES)).astype(np.float32)
    patch = (patch - patch.mean()) / (patch.std() + 1e-6)  # z-норма кадра
    return glob, patch.ravel()


def build_features() -> dict[str, np.ndarray]:
    """Извлечение признаков по всем сессиям (с кэшем в npz)."""
    if os.path.exists(CACHE):
        cached = np.load(CACHE, allow_pickle=False)
        if int(cached["content_res"]) == CONTENT_RES:
            return {k: cached[k] for k in cached.files}

    sessions = sorted(
        d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d))
    )
    x_glob, x_cont, y, groups, order = [], [], [], [], []
    for gid, sess in enumerate(sessions):
        label = session_label(sess)
        frames_dir = os.path.join(ROOT, sess, "frames")
        files = sorted(
            f for f in os.listdir(frames_dir) if f.lower().endswith(".jpg")
        )
        for idx, fn in enumerate(files):
            feats = _frame_features(os.path.join(frames_dir, fn))
            if feats is None:
                continue
            glob, cont = feats
            x_glob.append(glob)
            x_cont.append(cont)
            y.append(label)
            groups.append(gid)
            order.append(idx / max(1, len(files) - 1))  # позиция во времени 0..1

    data = {
        "x_glob": np.asarray(x_glob, dtype=np.float32),
        "x_cont": np.asarray(x_cont, dtype=np.float32),
        "y": np.asarray(y, dtype=np.int64),
        "groups": np.asarray(groups, dtype=np.int64),
        "order": np.asarray(order, dtype=np.float32),
        "sessions": np.asarray(sessions),
        "content_res": np.asarray(CONTENT_RES),
    }
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    np.savez(CACHE, **data)
    return data


def _model() -> object:
    """Простой прозрачный классификатор: масштабирование + логрегрессия."""
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=SEED
        ),
    )


def _report(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> None:
    """Печать метрик для одного разбиения."""
    acc = accuracy_score(y_true, y_pred)
    classes = np.unique(y_true)
    line = f"  [{name}] n={len(y_true)} acc={acc*100:5.1f}%"
    if len(classes) == 2:
        bacc = balanced_accuracy_score(y_true, y_pred)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        # recall по классам
        rec0 = cm[0, 0] / cm[0].sum() if cm[0].sum() else 0.0
        rec1 = cm[1, 1] / cm[1].sum() if cm[1].sum() else 0.0
        line += (
            f" bal_acc={bacc*100:5.1f}% recall(good=0)={rec0*100:5.1f}% "
            f"recall(bad=1)={rec1*100:5.1f}% CM={cm.tolist()}"
        )
    else:
        only = int(classes[0])
        frac = (y_pred == only).mean()
        line += (
            f" (только класс {only} в test) "
            f"предсказано верно={frac*100:5.1f}%"
        )
    print(line)


def protocol_random(x: np.ndarray, y: np.ndarray) -> None:
    """A. Случайный 5-fold — НЕЧЕСТНО (утечка почти-дубликатов)."""
    print("\nA. RANDOM 5-fold (LEAKY — для контраста, НЕ доверять):")
    skf = StratifiedKFold(5, shuffle=True, random_state=SEED)
    yt, yp = [], []
    for tr, te in skf.split(x, y):
        clf = _model().fit(x[tr], y[tr])
        yt.append(y[te])
        yp.append(clf.predict(x[te]))
    _report("random-cv", np.concatenate(yt), np.concatenate(yp))


def protocol_temporal(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray, order: np.ndarray
) -> None:
    """B. Temporal per-session holdout: train<0.6, gap, test>=0.7."""
    print("\nB. TEMPORAL per-session holdout (train=начало, test=хвост, gap):")
    tr = order < 0.6
    te = order >= 0.7
    clf = _model().fit(x[tr], y[tr])
    _report("temporal", y[te], clf.predict(x[te]))


def protocol_loso(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray, sessions: np.ndarray
) -> None:
    """C. Leave-one-session-out — перенос на другую запись."""
    print("\nC. LEAVE-ONE-SESSION-OUT (единственный честный тест переноса):")
    for gid in np.unique(groups):
        te = groups == gid
        tr = ~te
        if len(np.unique(y[tr])) < 2:
            print(
                f"  [held={sessions[gid]}] ПРОПУСК: в train остался один класс "
                f"(класс 0 всего в одной сессии) — обучение вырождено"
            )
            # всё равно показываем, что модель предскажет
            clf = _model().fit(x[tr], y[tr])
            _report(f"held={sessions[gid]}", y[te], clf.predict(x[te]))
            continue
        clf = _model().fit(x[tr], y[tr])
        _report(f"held={sessions[gid]}", y[te], clf.predict(x[te]))


def main() -> None:
    data = build_features()
    x_glob = data["x_glob"]
    x_cont = data["x_cont"]
    y = data["y"]
    groups = data["groups"]
    order = data["order"]
    sessions = data["sessions"]

    x_full = np.hstack([x_glob, x_cont])
    print(
        f"кадров={len(y)}  признаков: global={x_glob.shape[1]} "
        f"content={x_cont.shape[1]}  классы: bad(1)={int((y==1).sum())} "
        f"good(0)={int((y==0).sum())}"
    )

    print("\n" + "=" * 70)
    print("ПРОБА КОНФАУНДИНГА: логрегрессия только на 2 глоб. признаках (V, S)")
    print("=" * 70)
    x2 = x_glob[:, [0, 2]]  # meanV, meanS
    protocol_random(x2, y)
    protocol_temporal(x2, y, groups, order)
    protocol_loso(x2, y, groups, sessions)

    print("\n" + "=" * 70)
    print("ПОЛНАЯ МОДЕЛЬ: global + content (brightness-invariant) признаки")
    print("=" * 70)
    protocol_random(x_full, y)
    protocol_temporal(x_full, y, groups, order)
    protocol_loso(x_full, y, groups, sessions)

    print("\n" + "=" * 70)
    print("CONTENT-ONLY: только структура (без глобальной яркости/насыщенности)")
    print("=" * 70)
    protocol_loso(x_cont, y, groups, sessions)


if __name__ == "__main__":
    main()
