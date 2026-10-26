"""The uncertainty conversions both ways, over every distribution both formats know."""

from __future__ import annotations

import math

import olca_schema as o
import pytest

from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model.entities import Uncertainty
from ecosemantic.package.olca import from_olca_uncertainty, to_olca_uncertainty, uncertainty_refusal

_OWNER = "'p', exchange of 'f'"


def test_none_stays_none_in_both_directions() -> None:
    assert to_olca_uncertainty(None) is None
    assert from_olca_uncertainty(None, 1.0, owner=_OWNER) is None
    assert from_olca_uncertainty(o.Uncertainty(), 1.0, owner=_OWNER) is None


def test_every_model_distribution_becomes_its_openlca_counterpart() -> None:
    lognormal = to_olca_uncertainty(
        Uncertainty(type="lognormal", params={"loc": 0.5, "scale": 0.1})
    )
    assert lognormal is not None
    assert lognormal.distribution_type == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
    assert lognormal.geom_mean == pytest.approx(math.exp(0.5))
    assert lognormal.geom_sd == pytest.approx(math.exp(0.1))

    normal = to_olca_uncertainty(Uncertainty(type="normal", params={"loc": 2.0, "scale": 0.5}))
    assert normal is not None
    assert normal.distribution_type == o.UncertaintyType.NORMAL_DISTRIBUTION
    assert normal.mean == 2.0 and normal.sd == 0.5

    uniform = to_olca_uncertainty(
        Uncertainty(type="uniform", params={"minimum": 1.0, "maximum": 3.0})
    )
    assert uniform is not None
    assert uniform.distribution_type == o.UncertaintyType.UNIFORM_DISTRIBUTION
    assert uniform.minimum == 1.0 and uniform.maximum == 3.0

    triangular = to_olca_uncertainty(
        Uncertainty(type="triangular", params={"minimum": 0.0, "loc": 1.0, "maximum": 4.0})
    )
    assert triangular is not None
    assert triangular.distribution_type == o.UncertaintyType.TRIANGLE_DISTRIBUTION
    assert triangular.minimum == 0.0 and triangular.mode == 1.0 and triangular.maximum == 4.0


def test_every_openlca_distribution_becomes_its_model_counterpart() -> None:
    lognormal = from_olca_uncertainty(
        o.Uncertainty(
            distribution_type=o.UncertaintyType.LOG_NORMAL_DISTRIBUTION,
            geom_mean=math.exp(0.5),
            geom_sd=math.exp(0.1),
        ),
        math.exp(0.5),
        owner=_OWNER,
    )
    assert lognormal is not None
    assert lognormal.type == "lognormal"
    assert lognormal.params["loc"] == pytest.approx(0.5)
    assert lognormal.params["scale"] == pytest.approx(0.1)

    normal = from_olca_uncertainty(
        o.Uncertainty(distribution_type=o.UncertaintyType.NORMAL_DISTRIBUTION, mean=2.0, sd=0.5),
        2.0,
        owner=_OWNER,
    )
    assert normal == Uncertainty(type="normal", params={"loc": 2.0, "scale": 0.5})

    uniform = from_olca_uncertainty(
        o.Uncertainty(
            distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION, minimum=1.0, maximum=3.0
        ),
        2.0,
        owner=_OWNER,
    )
    assert uniform == Uncertainty(type="uniform", params={"minimum": 1.0, "maximum": 3.0})

    triangular = from_olca_uncertainty(
        o.Uncertainty(
            distribution_type=o.UncertaintyType.TRIANGLE_DISTRIBUTION,
            minimum=0.0,
            mode=1.0,
            maximum=4.0,
        ),
        1.0,
        owner=_OWNER,
    )
    assert triangular == Uncertainty(
        type="triangular", params={"minimum": 0.0, "loc": 1.0, "maximum": 4.0}
    )


def test_a_distribution_without_a_counterpart_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        from_olca_uncertainty(
            o.Uncertainty(distribution_type="no such distribution"), 1.0, owner=_OWNER
        )


def _lognormal(geom_mean: float | None, geom_sd: float | None) -> o.Uncertainty:
    return o.Uncertainty(
        distribution_type=o.UncertaintyType.LOG_NORMAL_DISTRIBUTION,
        geom_mean=geom_mean,
        geom_sd=geom_sd,
    )


def test_a_lognormal_without_spread_is_no_distribution() -> None:
    # BAFU:2026 carries 2 833 of these: geomSd 1
    assert from_olca_uncertainty(_lognormal(1.0, 1.0), 1.0, owner=_OWNER) is None
    assert from_olca_uncertainty(_lognormal(-1.0, 1.0), 1.0, owner=_OWNER) is None


def test_a_lognormals_sign_follows_its_exchanges_amount() -> None:
    # openLCA exports carry -|amount| as geomMean on 14 136 positive amounts
    mirrored = from_olca_uncertainty(_lognormal(-0.0023, math.sqrt(2)), 0.0023, owner=_OWNER)
    assert mirrored is not None and mirrored.centre() == pytest.approx(0.0023)
    assert mirrored.params["scale"] == pytest.approx(math.log(math.sqrt(2)))
    negative = from_olca_uncertainty(_lognormal(4.5946, 1.1), -4.5946, owner=_OWNER)
    assert negative is not None and negative.centre() == pytest.approx(-4.5946)


def test_a_zero_amount_samples_nothing() -> None:
    assert from_olca_uncertainty(_lognormal(0.0, 7.7), 0.0, owner=_OWNER) is None


@pytest.mark.parametrize(
    ("geom_mean", "geom_sd", "amount", "named"),
    [
        (1.0, 0.9, 1.0, "geomSd 0.9"),
        (0.0, 1.5, 2.0, "geomMean 0.0"),
        (None, 1.5, 2.0, "geomMean None"),
    ],
)
def test_a_lognormal_that_is_no_distribution_is_invalid(
    geom_mean: float | None, geom_sd: float, amount: float, named: str
) -> None:
    with pytest.raises(Invalid, match=named):
        from_olca_uncertainty(_lognormal(geom_mean, geom_sd), amount, owner=_OWNER)


def test_a_uniform_whose_bounds_meet_cannot_be_held() -> None:
    u = o.Uncertainty(
        distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION, minimum=0.0, maximum=0.0
    )
    reason = uncertainty_refusal(u, 1.0)
    assert reason is not None and "minimum must be less than maximum" in reason


def test_a_triangle_out_of_order_cannot_be_held() -> None:
    u = o.Uncertainty(
        distribution_type=o.UncertaintyType.TRIANGLE_DISTRIBUTION,
        minimum=8.8,
        mode=8.6,
        maximum=8.4,
    )
    assert uncertainty_refusal(u, 8.6) is not None


def test_a_lognormal_with_a_zero_geometric_mean_cannot_be_held() -> None:
    reason = uncertainty_refusal(_lognormal(0.0, 1.5), 2.0)
    assert reason is not None and "geomMean" in reason


def test_a_distribution_the_core_holds_has_no_refusal() -> None:
    assert uncertainty_refusal(None, 1.0) is None
    assert uncertainty_refusal(_lognormal(2.0, 1.2), 2.0) is None


def test_a_refused_distribution_is_invalid_and_names_its_owner() -> None:
    u = o.Uncertainty(
        distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION, minimum=0.0, maximum=0.0
    )
    with pytest.raises(Invalid, match="'p', exchange of 'f'"):
        from_olca_uncertainty(u, 1.0, owner="'p', exchange of 'f'")
