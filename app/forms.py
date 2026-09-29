"""Hilfsfunktionen zum Auswerten von HTML-Formularwerten."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TypeVar

E = TypeVar("E")


def to_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def to_int(value: str | None) -> int | None:
    value = to_str(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def to_decimal(value: str | None) -> Decimal | None:
    value = to_str(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def to_date(value: str | None) -> date | None:
    value = to_str(value)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def to_enum(enum_cls: type[E], value: str | None, default: E | None = None) -> E | None:
    value = to_str(value)
    if value is None:
        return default
    try:
        return enum_cls(value)  # type: ignore[call-arg]
    except ValueError:
        return default
