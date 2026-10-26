"""Uncertainty as openLCA writes it, and back: shared by the package's readers and writers."""

from __future__ import annotations

import math

import olca_schema as o
from pydantic import ValidationError

from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model.entities import Uncertainty, UncertaintyType


def to_olca_uncertainty(u: Uncertainty | None) -> o.Uncertainty | None:
    """An openLCA distribution for a model uncertainty."""
    if u is None:
        return None
    p = u.params
    if u.type == "lognormal":
        return o.Uncertainty(
            distribution_type=o.UncertaintyType.LOG_NORMAL_DISTRIBUTION,
            geom_mean=math.exp(float(p["loc"])),
            geom_sd=math.exp(float(p["scale"])),
        )
    if u.type == "normal":
        return o.Uncertainty(
            distribution_type=o.UncertaintyType.NORMAL_DISTRIBUTION,
            mean=float(p["loc"]),
            sd=float(p["scale"]),
        )
    if u.type == "uniform":
        return o.Uncertainty(
            distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION,
            minimum=float(p["minimum"]),
            maximum=float(p["maximum"]),
        )
    return o.Uncertainty(
        distribution_type=o.UncertaintyType.TRIANGLE_DISTRIBUTION,
        minimum=float(p["minimum"]),
        mode=float(p["loc"]),
        maximum=float(p["maximum"]),
    )


def _lognormal_reason(u: o.Uncertainty, amount: float) -> str | None:
    """Why a lognormal on an exchange of this amount cannot be held, or None when it can: a
    geometric standard deviation below 1 has no spread a distribution can take, and a geometric
    mean of 0 or none has no centre."""
    if amount == 0:
        return None
    if u.geom_sd is None or u.geom_sd < 1:
        return f"a lognormal with geomSd {u.geom_sd} has no spread a distribution can take"
    if u.geom_mean is None or u.geom_mean == 0:
        return f"a lognormal with geomMean {u.geom_mean} cannot centre amount {amount}"
    return None


def _lognormal(u: o.Uncertainty, amount: float) -> Uncertainty | None:
    """The model's lognormal for an openLCA one on an exchange of this amount, or None when it
    samples nothing: a zero amount, or a geometric standard deviation of 1. The geometric mean and
    deviation are the ones `_lognormal_reason` held."""
    if amount == 0 or u.geom_sd == 1:
        return None
    params: dict[str, float | bool] = {
        "loc": math.log(abs(u.geom_mean)),
        "scale": math.log(u.geom_sd),
    }
    if amount < 0:
        params["negative"] = True
    return Uncertainty(type="lognormal", params=params)


def _params(u: o.Uncertainty) -> tuple[UncertaintyType, dict[str, float | bool | None]] | None:
    """The model's type and params that an openLCA distribution's fields name; None for a
    lognormal, whose params follow the exchange's amount, and for a type the model does not have."""
    t = u.distribution_type
    if t == o.UncertaintyType.NORMAL_DISTRIBUTION:
        return ("normal", {"loc": u.mean, "scale": u.sd})
    if t == o.UncertaintyType.UNIFORM_DISTRIBUTION:
        return ("uniform", {"minimum": u.minimum, "maximum": u.maximum})
    if t == o.UncertaintyType.TRIANGLE_DISTRIBUTION:
        return ("triangular", {"minimum": u.minimum, "loc": u.mode, "maximum": u.maximum})
    return None


def _model_reason(type: UncertaintyType, params: dict[str, float | bool | None]) -> str | None:
    """The model validator's complaint about these params, without pydantic's prefix, or None
    when the model holds them."""
    try:
        Uncertainty(type=type, params=params)
    except ValidationError as error:
        return error.errors()[0]["msg"].removeprefix("Value error, ")
    return None


def _held(u: o.Uncertainty, amount: float) -> Uncertainty | None:
    """The model distribution for an openLCA one, or None when it samples nothing; the params are
    the ones `uncertainty_refusal` held, and a type with no counterpart is NotSupported."""
    if u.distribution_type == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION:
        return _lognormal(u, amount)
    known = _params(u)
    if known is None:
        raise NotSupported(f"openLCA distribution {u.distribution_type} has no counterpart")
    type, params = known
    return Uncertainty(type=type, params=params)


def uncertainty_refusal(u: o.Uncertainty | None, amount: float) -> str | None:
    """Why the core cannot hold this distribution on an exchange of this amount, or None when it
    can, including when there is none to hold. A distribution type with no counterpart is no
    refusal of its values: `from_olca_uncertainty` answers that one NotSupported."""
    if u is None or u.distribution_type is None:
        return None
    if u.distribution_type == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION:
        return _lognormal_reason(u, amount)
    known = _params(u)
    if known is None:
        return None
    type, params = known
    return _model_reason(type, params)


def from_olca_uncertainty(
    u: o.Uncertainty | None, amount: float, *, owner: str
) -> Uncertainty | None:
    """A model uncertainty for an openLCA distribution on an exchange of this amount; None for
    none. A lognormal's sign is the amount's, since openLCA exports carry the geometric mean of a
    positive amount as its negative; a geometric standard deviation of 1 and a zero amount
    sample nothing. Invalid names owner and why the core cannot hold the distribution;
    NotSupported when openLCA's distribution type has no counterpart."""
    if reason := uncertainty_refusal(u, amount):
        raise Invalid(f"{owner}: {reason}")
    if u is None or u.distribution_type is None:
        return None
    return _held(u, amount)
