"""Deterministic JSON for MoneyLab's internal typed analysis records."""

from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
from types import UnionType
from typing import get_args, get_origin, get_type_hints


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value:
            return "0"
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def dumps(record) -> str:
    return json.dumps(_encode(record), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate snapshot key {key!r}")
        result[key] = value
    return result


def _decode(value, target):
    origin = get_origin(target)
    if origin is UnionType:
        for option in get_args(target):
            try:
                return _decode(value, option)
            except ValueError:
                continue
        raise ValueError(f"invalid value for {target}")
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("expected a JSON array")
        item_type, _ = get_args(target)
        return tuple(_decode(item, item_type) for item in value)
    if is_dataclass(target):
        types = get_type_hints(target)
        if not isinstance(value, dict) or value.keys() != types.keys():
            raise ValueError(f"unexpected fields for {target.__name__}")
        return target(**{name: _decode(value[name], kind) for name, kind in types.items()})

    if target is Decimal and isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("expected a decimal string") from exc
    if target is date and isinstance(value, str):
        return date.fromisoformat(value)
    if issubclass(target, Enum) and isinstance(value, str):
        return target(value)
    if type(value) is target:
        return value
    raise ValueError(f"invalid value for {target.__name__}")


def loads(payload: str, record_type):
    return _decode(json.loads(payload, object_pairs_hook=_unique_object), record_type)
