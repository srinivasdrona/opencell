"""Smoke test: verify OpenCell imports and dependencies."""

import opencell


def test_version() -> None:
    assert opencell.__version__ == "0.1.0"


def test_jax_float64() -> None:
    import jax
    import jax.numpy as jnp

    jax.config.update("jax_enable_x64", True)
    x = jnp.array([1.0], dtype=jnp.float64)
    assert x.dtype == jnp.float64


def test_pint_units() -> None:
    import pint

    ureg = pint.UnitRegistry()
    km = 0.5 * ureg.mM
    assert km.magnitude == 0.5
    assert str(km.units) == "millimolar"
