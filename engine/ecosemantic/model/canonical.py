"""The result-relevant projection of a product system, and the hash that names its version."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from pydantic import JsonValue

from ecosemantic.model.entities import Exchange, ProductSystem
from ecosemantic.model.refs import ExchangeInput


def significant(value: float) -> str:
    """A number at the twelve significant digits a content hash and a change log compare it at."""
    return f"{value:.12g}"


def _number(value: float) -> str:
    return format(Decimal(significant(value)).normalize(), "f")


def _uncertainty(exchange: Exchange) -> dict[str, JsonValue] | None:
    if exchange.uncertainty is None:
        return None
    params = {
        key: (value if isinstance(value, bool) else _number(float(value)))
        for key, value in sorted(exchange.uncertainty.params.items())
    }
    return {"type": exchange.uncertainty.type, "params": params}


def _input(ref: ExchangeInput | None) -> list[str]:
    if ref is None:
        return []
    data = ref.model_dump(exclude_none=True)
    return [str(data.pop("kind"))] + [str(data[key]) for key in sorted(data)]


def _exchange(code: str, exchange: Exchange) -> dict[str, JsonValue]:
    return {
        "process": code,
        "type": exchange.type,
        "input": _input(exchange.input),
        "name": exchange.name,
        "unit": exchange.unit,
        "amount": _number(exchange.amount),
        "formula": exchange.formula,
        "uncertainty": _uncertainty(exchange),
    }


def canonical_model(product_system: ProductSystem) -> list[list[dict[str, JsonValue]]]:
    """The processes and the exchanges of the canonical projection: the model, without the
    parameter space."""
    processes: list[dict[str, JsonValue]] = sorted(
        (
            {
                "code": a.code,
                "name": a.name,
                "unit": a.unit,
                "location": a.location,
                "reference_product": a.reference_product,
            }
            for a in product_system.processes
        ),
        key=lambda a: str(a["code"]),
    )
    exchanges: list[dict[str, JsonValue]] = sorted(
        (_exchange(a.code, e) for a in product_system.processes for e in a.exchanges),
        key=lambda e: json.dumps(e, sort_keys=True, default=str),
    )
    return [processes, exchanges]


def canonical(product_system: ProductSystem) -> list[list[dict[str, JsonValue]]]:
    """Processes, exchanges, parameters, cases, the reference process and the database build
    the system names, with only the fields that change a result; a system naming no build
    keeps the projection it has without one."""
    parameters: list[dict[str, JsonValue]] = sorted(
        (
            {
                "name": p.name,
                "value": None if p.value is None else _number(p.value),
                "formula": p.formula,
            }
            for p in product_system.parameters
        ),
        key=lambda p: str(p["name"]),
    )
    cases: list[dict[str, JsonValue]] = sorted(
        (
            {"name": c.name, "values": {k: _number(v) for k, v in sorted(c.values.items())}}
            for c in product_system.cases
        ),
        key=lambda c: str(c["name"]),
    )
    named: dict[str, JsonValue] = {"reference_process": product_system.reference_process}
    if product_system.database.fingerprint is not None:
        named["fingerprint"] = product_system.database.fingerprint
    return [*canonical_model(product_system), parameters, cases, [named]]


def _digest(projection: list[list[dict[str, JsonValue]]]) -> str:
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(product_system: ProductSystem) -> str:
    """SHA-256 of the canonical projection: the name of a version."""
    return _digest(canonical(product_system))


def base_pin(product_system: ProductSystem) -> str:
    """SHA-256 of the canonical projection without the cases: what a scenario and a link naming
    no case compute over, so a case written or deleted moves neither."""
    processes, exchanges, parameters, _, reference = canonical(product_system)
    return _digest([processes, exchanges, parameters, reference])
