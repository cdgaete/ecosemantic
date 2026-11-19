"""Uncertainty as openLCA writes it, and back: shared by the package's readers and writers."""

from __future__ import annotations

import math

import olca_schema as o
from pydantic import BaseModel, ValidationError

from ecosemantic.errors import Invalid, NotSupported, said
from ecosemantic.model.entities import REQUIRED_PARAMS, Uncertainty, UncertaintyType


class WrittenLognormal(BaseModel):
    """A lognormal's parameters as they were written, which the geometric mean and deviation
    return only within their last place."""

    loc: float
    scale: float


class Bounds(BaseModel):
    """The range openLCA writes for a uniform and a triangular and holds nowhere for a lognormal
    and a normal, either end None where the distribution states none."""

    minimum: float | None = None
    maximum: float | None = None


def _states_its_range(uncertainty: Uncertainty) -> bool:
    """Whether the type's own required params are its range, as a uniform's and a triangular's
    are, so openLCA writes the bounds itself."""
    return REQUIRED_PARAMS[uncertainty.type] >= {"minimum", "maximum"}


def bounds_of(uncertainty: Uncertainty | None) -> Bounds | None:
    """The bounds a lognormal or a normal states, either of them None where it states none; None
    for a uniform or a triangular, whose range openLCA writes itself, and for no distribution."""
    if uncertainty is None or _states_its_range(uncertainty):
        return None
    low, high = uncertainty.bounds()
    return None if low is None and high is None else Bounds(minimum=low, maximum=high)


def bounded(uncertainty: Uncertainty | None, bounds: Bounds | None) -> Uncertainty | None:
    """The distribution carrying these bounds, or as it stands for none."""
    if uncertainty is None or bounds is None:
        return uncertainty
    params: dict[str, float | bool] = dict(uncertainty.params)
    if bounds.minimum is not None:
        params["minimum"] = bounds.minimum
    if bounds.maximum is not None:
        params["maximum"] = bounds.maximum
    return Uncertainty(type=uncertainty.type, params=params)


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


def _as_written(written: float | None, held: float) -> float:
    """A lognormal parameter as it was written when its exponential is the value the package
    holds, and the logarithm of the value the package holds otherwise: an edit in openLCA reads as
    the edit."""
    if written is not None and math.exp(written) == held:
        return written
    return math.log(held)


def _lognormal(
    u: o.Uncertainty, amount: float, written: WrittenLognormal | None = None
) -> Uncertainty | None:
    """The model's lognormal for an openLCA one on an exchange of this amount, or None when it
    samples nothing: a zero amount, or a geometric standard deviation of 1. Each of loc and scale
    is the written one whenever its exponential is the value the package holds, and the logarithm
    of that value otherwise, as `_as_written` decides."""
    if amount == 0 or u.geom_sd == 1:
        return None
    loc = written.loc if written is not None else None
    scale = written.scale if written is not None else None
    params: dict[str, float | bool] = {
        "loc": _as_written(loc, abs(u.geom_mean)),
        "scale": _as_written(scale, u.geom_sd),
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
        return said(error.errors()[0]["msg"])
    return None


def _held(u: o.Uncertainty, amount: float, written: WrittenLognormal | None) -> Uncertainty | None:
    """The model distribution for an openLCA one, or None when it samples nothing; the params are
    the ones `uncertainty_refusal` held, a lognormal's read as `_lognormal` reads them, and a type
    with no counterpart is NotSupported."""
    if u.distribution_type == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION:
        return _lognormal(u, amount, written)
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
    u: o.Uncertainty | None,
    amount: float,
    *,
    owner: str,
    written: WrittenLognormal | None = None,
) -> Uncertainty | None:
    """A model uncertainty for an openLCA distribution on an exchange of this amount; None for
    none. A lognormal's sign is the amount's, since openLCA exports carry the geometric mean of a
    positive amount as its negative; a geometric standard deviation of 1 and a zero amount
    sample nothing. A lognormal's loc and scale are the ones written in the package whenever their
    exponentials are the geometric mean and deviation it holds, and the logarithms of those
    otherwise. Invalid names owner and why the core cannot hold the distribution; NotSupported
    when openLCA's distribution type has no counterpart."""
    if reason := uncertainty_refusal(u, amount):
        raise Invalid(f"{owner}: {reason}")
    if u is None or u.distribution_type is None:
        return None
    return _held(u, amount, written)
