import sys

import pytest

from athenian.api.controllers.features.entries import \
    CalculatorNotReadyException, make_calculator, \
    MetricEntriesCalculator as OriginalMetricEntriesCalculator


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

    def is_ready_for(self, account, meta_ids) -> bool:
        """Check whether the calculator is ready for the given account and meta ids."""
        return account == 1


def test_get_calculator_no_variation(base_testing_module, mdb, pdb, rdb, cache):
    calc = make_calculator(
        None, 365, 1, (1, ), mdb, pdb, rdb, cache, base_module=base_testing_module,
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_missing_module_no_error(mdb, pdb, rdb, cache):
    calc = make_calculator(
        "test_entries", 365, 1, (1, ), mdb, pdb, rdb, cache, base_module="missing_module",
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_missing_implementation_no_error(
    base_testing_module, mdb, pdb, rdb, cache,
):
    calc = make_calculator(
        "api", 365, 1, (1, ), mdb, pdb, rdb, cache, base_module="athenian",
    )
    assert isinstance(calc, OriginalMetricEntriesCalculator)


def test_get_calculator_variation_found(
    base_testing_module, current_module, mdb, pdb, rdb, cache,
):
    calc = make_calculator(
        "test_entries", 365, 1, (1, ), mdb, pdb, rdb, cache, base_module=base_testing_module,
    )
    assert isinstance(calc, MetricEntriesCalculator)

    with pytest.raises(CalculatorNotReadyException):
        make_calculator(
            "test_entries", 365, 2, (1, ), mdb, pdb, rdb, cache, base_module=base_testing_module,
        )
