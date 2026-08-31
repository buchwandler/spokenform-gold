from __future__ import annotations

import datetime as _dt
import ipaddress
import re
from typing import Any

DECIMAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
SEMVER_RE = re.compile(
    r"^(?:v)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


def _as_int(mapping: dict[str, Any], key: str) -> int | None:
    value = mapping.get(key)
    return value if isinstance(value, int) else None


def _validate_date(semantic: dict[str, Any]) -> list[str]:
    if "candidates" in semantic:
        errors: list[str] = []
        candidates = semantic.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return ["date candidates must be a non-empty list"]
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                errors.append(f"date candidate[{index}] must be an object")
                continue
            for error in _validate_date(candidate):
                errors.append(f"date candidate[{index}]: {error}")
        return errors
    year = _as_int(semantic, "year")
    month = semantic.get("month")
    day = semantic.get("day")
    precision = semantic.get("precision")
    if year is None:
        return ["date semantic requires integer year"]
    if month is not None and not isinstance(month, int):
        return ["date semantic month must be an integer when present"]
    if day is not None and not isinstance(day, int):
        return ["date semantic day must be an integer when present"]
    if day is not None and month is None:
        return ["date semantic day requires month"]
    expected_precision = (
        "day" if day is not None else "month" if month is not None else "year"
    )
    if precision is not None and precision != expected_precision:
        return [f"date semantic precision must be {expected_precision!r}"]
    if month is not None and not 1 <= month <= 12:
        return [f"date month out of range: {month}"]
    if day is not None:
        try:
            _dt.date(year, month, day)
        except ValueError as exc:
            return [f"invalid date semantic: {exc}"]
    elif not 1 <= year <= 9999:
        return [f"date year out of range: {year}"]
    return []


def _validate_time(semantic: dict[str, Any]) -> list[str]:
    hour = _as_int(semantic, "hour")
    minute = _as_int(semantic, "minute")
    if None in {hour, minute}:
        return ["time semantic requires integer hour and minute"]
    second = semantic.get("second", 0)
    if not isinstance(second, int):
        return ["time semantic second must be an integer"]
    if not 0 <= hour <= 23:
        return [f"time hour out of range: {hour}"]
    if not 0 <= minute <= 59:
        return [f"time minute out of range: {minute}"]
    if not 0 <= second <= 59:
        return [f"time second out of range: {second}"]
    return []


def _validate_decimal(semantic: dict[str, Any]) -> list[str]:
    value = semantic.get("value")
    if isinstance(value, str) and DECIMAL_RE.fullmatch(value):
        return []
    integer = semantic.get("integer")
    nonrepeating = semantic.get("nonrepeating")
    repeating = semantic.get("repeating")
    if (
        not isinstance(integer, str)
        or not re.fullmatch(r"[+-]?\d+", integer)
        or not isinstance(nonrepeating, str)
        or not re.fullmatch(r"\d*", nonrepeating)
        or not isinstance(repeating, str)
        or not re.fullmatch(r"\d+", repeating)
    ):
        return [
            "decimal semantic requires exact string value or integer/nonrepeating/repeating digits"
        ]
    return []


def _validate_fraction(semantic: dict[str, Any]) -> list[str]:
    numerator = _as_int(semantic, "numerator")
    denominator = _as_int(semantic, "denominator")
    if None in {numerator, denominator}:
        return ["fraction semantic requires integer numerator and denominator"]
    if denominator == 0:
        return ["fraction denominator must not be 0"]
    return []


def _validate_currency(semantic: dict[str, Any]) -> list[str]:
    currency = semantic.get("currency")
    major = _as_int(semantic, "major")
    minor = _as_int(semantic, "minor")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        return ["currency semantic requires ISO-style 3-letter currency code"]
    if None in {major, minor}:
        return ["currency semantic requires integer major and minor values"]
    if not 0 <= minor <= 99:
        return [f"currency minor out of range: {minor}"]
    return []


def _validate_ip_address(semantic: dict[str, Any]) -> list[str]:
    address = semantic.get("address")
    if not isinstance(address, str):
        return ["ip_address semantic requires address string"]
    try:
        ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError as exc:
        return [f"invalid IPv4 address: {exc}"]
    return []


def _validate_version(semantic: dict[str, Any]) -> list[str]:
    if all(isinstance(semantic.get(name), int) for name in ("major", "minor", "patch")):
        prerelease = semantic.get("prerelease")
        if prerelease is not None and not isinstance(prerelease, str):
            return ["version prerelease must be a string"]
        return []
    value = semantic.get("value")
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        return [
            "version semantic requires major/minor/patch integers or a semantic-version string"
        ]
    return []


def _validate_identifier(semantic: dict[str, Any]) -> list[str]:
    value = semantic.get("value", semantic.get("text"))
    if not isinstance(value, str) or not value.strip():
        return ["identifier semantic requires non-empty value/text"]
    return []


VALIDATORS = {
    "date": _validate_date,
    "time": _validate_time,
    "decimal": _validate_decimal,
    "fraction": _validate_fraction,
    "currency": _validate_currency,
    "ip_address": _validate_ip_address,
    "version": _validate_version,
    "identifier": _validate_identifier,
}


def validate_semantic(category: str, semantic: Any) -> list[str]:
    if category not in VALIDATORS:
        return []
    if not isinstance(semantic, dict):
        return [f"{category} semantic must be an object"]
    return VALIDATORS[category](semantic)
