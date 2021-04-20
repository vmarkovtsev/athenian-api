import sys

import pytest

from athenian.api.controllers.features.entries import \
    get_calculator, MetricEntriesCalculator as OriginalMetricEntriesCalculator


@pytest.fixture
def current_module():
    return sys.modules[__name__].__name__


@pytest.fixture
def base_testing_module(current_module):
    return current_module[: current_module.rfind(".")]


class MetricEntriesCalculator:
    """Fake calculator for different metrics."""

    def __init__(self, *args) -> "MetricEntriesCalculator":
        """Create a `MetricEntriesCalculator`."""
        pass


def test_get_calculator_no_variation(base_testing_module, mdb, pdb, rdb, cache):
    calc = get_calculator(
        "github", 1, (1, ), mdb, pdb, rdb, cache, base_module=base_testing_module,
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_missing_module_no_error(mdb, pdb, rdb, cache):
    calc = get_calculator(
        "github", 1, (1, ), mdb, pdb, rdb, cache,
        variation="test_entries", base_module="missing_module",
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_missing_implementation_no_error(
    base_testing_module, mdb, pdb, rdb, cache,
):
    calc = get_calculator(
        "github", 1, (1, ), mdb, pdb, rdb, cache, variation="api", base_module="athenian",
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_raise_error(base_testing_module, mdb, pdb, rdb, cache):
    try:
        get_calculator(
            "github", 1, (1, ), mdb, pdb, rdb, cache,
            variation="test_entries", base_module="missing_module", raise_err=True,
        )
    except ModuleNotFoundError:
        assert True
    else:
        raise AssertionError("Expected ModuleNotFoundError not raised")

    try:
        get_calculator(
            "github", 1, (1, ), mdb, pdb, rdb, cache,
            variation="api", base_module="athenian", raise_err=True,
        )
    except RuntimeError:
        assert True
    else:
        raise AssertionError("Expected RuntimeError not raised")


def test_get_calculator_variation_found(
    base_testing_module, current_module, mdb, pdb, rdb, cache,
):
    calc = get_calculator(
        "github", 1, (1, ), mdb, pdb, rdb, cache,
        variation="test_entries", base_module=base_testing_module,
    )
    assert isinstance(calc, MetricEntriesCalculator)
