"""Тесты human_size и human_duration."""

from __future__ import annotations

import pytest

from plasma_dog.common.format import human_duration, human_size


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B"),
        (1, "1 B"),
        (999, "999 B"),
        (1_000, "1.0 KB"),
        (1_234, "1.2 KB"),
        (999_999, "1000.0 KB"),
    ],
)
def test_human_size_bytes_and_kb(value: int, expected: str) -> None:
    """Округление B -> KB и десятичный шаг 1000."""
    assert human_size(value) == expected


def test_human_size_mb() -> None:
    """Значение в районе единиц мегабайт."""
    assert human_size(1_500_000) == "1.5 MB"
    assert human_size(2_000_000) == "2.0 MB"


def test_human_size_gb() -> None:
    """Значения в районе единиц гигабайт."""
    assert human_size(1_200_000_000) == "1.2 GB"


def test_human_size_tb() -> None:
    """Большое значение должно подняться до TB."""
    assert human_size(3_400_000_000_000) == "3.4 TB"


def test_human_size_negative_is_zero() -> None:
    """Отрицательное число клампится в 0."""
    assert human_size(-100) == "0 B"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "00:00"),
        (5, "00:05"),
        (59, "00:59"),
        (60, "01:00"),
        (61, "01:01"),
        (3599, "59:59"),
    ],
)
def test_human_duration_seconds_and_minutes(value: float, expected: str) -> None:
    """До часа — формат MM:SS."""
    assert human_duration(value) == expected


def test_human_duration_hours() -> None:
    """От часа — формат HH:MM:SS."""
    assert human_duration(3600) == "01:00:00"
    assert human_duration(3661) == "01:01:01"
    assert human_duration(90000) == "25:00:00"


def test_human_duration_negative_is_zero() -> None:
    """Отрицательная длительность клампится в 0."""
    assert human_duration(-30) == "00:00"


def test_human_duration_fractional_seconds_truncated() -> None:
    """Дробная часть секунд игнорируется (округление вниз)."""
    assert human_duration(59.9) == "00:59"
