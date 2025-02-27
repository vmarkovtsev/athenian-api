from datetime import date
from typing import List, Optional

from athenian.api.models.web.base_model_ import Model
from athenian.api.models.web.calculated_pull_request_metrics_item import (
    CalculatedPullRequestMetricsItem,
)
from athenian.api.models.web.pull_request_metric_id import PullRequestMetricID


class CalculatedPullRequestMetrics(Model):
    """This class is auto generated by OpenAPI Generator (https://openapi-generator.tech)."""

    attribute_types = {
        "calculated": List[CalculatedPullRequestMetricsItem],
        "metrics": List[str],
        "date_from": date,
        "date_to": date,
        "timezone": int,
        "granularities": List[str],
        "quantiles": Optional[List[float]],
        "exclude_inactive": bool,
    }

    attribute_map = {
        "calculated": "calculated",
        "metrics": "metrics",
        "date_from": "date_from",
        "date_to": "date_to",
        "timezone": "timezone",
        "granularities": "granularities",
        "quantiles": "quantiles",
        "exclude_inactive": "exclude_inactive",
    }

    def __init__(
        self,
        calculated: Optional[List[CalculatedPullRequestMetricsItem]] = None,
        metrics: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        timezone: Optional[int] = None,
        granularities: Optional[List[str]] = None,
        quantiles: Optional[List[float]] = None,
        exclude_inactive: Optional[bool] = None,
    ):
        """CalculatedPullRequestMetrics - a model defined in OpenAPI

        :param calculated: The calculated of this CalculatedPullRequestMetrics.
        :param metrics: The metrics of this CalculatedPullRequestMetrics.
        :param date_from: The date_from of this CalculatedPullRequestMetrics.
        :param date_to: The date_to of this CalculatedPullRequestMetrics.
        :param granularities: The granularities of this CalculatedPullRequestMetrics.
        :param quantiles: The quantiles of this CalculatedPullRequestMetrics.
        :param exclude_inactive: The exclude_inactive of this CalculatedPullRequestMetrics.
        """
        self._calculated = calculated
        self._metrics = metrics
        self._date_from = date_from
        self._date_to = date_to
        self._timezone = timezone
        self._granularities = granularities
        self._quantiles = quantiles
        self._exclude_inactive = exclude_inactive

    @property
    def calculated(self) -> List[CalculatedPullRequestMetricsItem]:
        """Gets the calculated of this CalculatedPullRequestMetrics.

        The values of the requested metrics through time.

        :return: The calculated of this CalculatedPullRequestMetrics.
        """
        return self._calculated

    @calculated.setter
    def calculated(self, calculated: List[CalculatedPullRequestMetricsItem]):
        """Sets the calculated of this CalculatedPullRequestMetrics.

        The values of the requested metrics through time.

        :param calculated: The calculated of this CalculatedPullRequestMetrics.
        """
        if calculated is None:
            raise ValueError("Invalid value for `calculated`, must not be `None`")

        self._calculated = calculated

    @property
    def metrics(self) -> List[str]:
        """Gets the metrics of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.metrics`.

        :return: The metrics of this CalculatedPullRequestMetrics.
        """
        return self._metrics

    @metrics.setter
    def metrics(self, metrics: List[str]):
        """Sets the metrics of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.metrics`.

        :param metrics: The metrics of this CalculatedPullRequestMetrics.
        """
        if metrics is None:
            raise ValueError("Invalid value for `metrics`, must not be `None`")
        for m in metrics:
            if m not in PullRequestMetricID:
                raise ValueError(
                    'Invalid value for `metrics`: "%s" must be one of %s' % m,
                    list(PullRequestMetricID),
                )

        self._metrics = metrics

    @property
    def date_from(self) -> date:
        """Gets the date_from of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.date_from`.

        :return: The date_from of this CalculatedPullRequestMetrics.
        """
        return self._date_from

    @date_from.setter
    def date_from(self, date_from: date):
        """Sets the date_from of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.date_from`.

        :param date_from: The date_from of this CalculatedPullRequestMetrics.
        """
        if date_from is None:
            raise ValueError("Invalid value for `date_from`, must not be `None`")

        self._date_from = date_from

    @property
    def date_to(self) -> date:
        """Gets the date_to of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.date_to`.

        :return: The date_to of this CalculatedPullRequestMetrics.
        """
        return self._date_to

    @date_to.setter
    def date_to(self, date_to: date):
        """Sets the date_to of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.date_to`.

        :param date_to: The date_to of this CalculatedPullRequestMetrics.
        """
        if date_to is None:
            raise ValueError("Invalid value for `date_to`, must not be `None`")

        self._date_to = date_to

    @property
    def timezone(self) -> int:
        """Gets the timezone of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.timezone`.

        :return: The timezone of this CalculatedPullRequestMetrics.
        """
        return self._timezone

    @timezone.setter
    def timezone(self, timezone: int):
        """Sets the timezone of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.timezone`.

        :param timezone: The timezone of this CalculatedPullRequestMetrics.
        """
        if timezone is not None and timezone > 720:
            raise ValueError(
                "Invalid value for `timezone`, must be a value less than or equal to `720`",
            )
        if timezone is not None and timezone < -720:
            raise ValueError(
                "Invalid value for `timezone`, must be a value greater than or equal to `-720`",
            )

        self._timezone = timezone

    @property
    def granularities(self) -> List[str]:
        """Gets the granularities of this CalculatedPullRequestMetrics.

        :return: The granularities of this CalculatedPullRequestMetrics.
        """
        return self._granularities

    @granularities.setter
    def granularities(self, granularities: List[str]):
        """Sets the granularities of this CalculatedPullRequestMetrics.

        :param granularities: The granularities of this CalculatedPullRequestMetrics.
        """
        self._granularities = granularities

    @property
    def quantiles(self) -> Optional[List[float]]:
        """Gets the quantiles of this CalculatedPullRequestMetrics.

        :return: The quantiles of this CalculatedPullRequestMetrics.
        """
        return self._quantiles

    @quantiles.setter
    def quantiles(self, quantiles: Optional[List[float]]):
        """Sets the quantiles of this CalculatedPullRequestMetrics.

        :param quantiles: The quantiles of this CalculatedPullRequestMetrics.
        """
        self._quantiles = quantiles

    @property
    def exclude_inactive(self) -> bool:
        """Gets the exclude_inactive of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.exclude_inactive`.

        :return: The exclude_inactive of this CalculatedPullRequestMetrics.
        """
        return self._exclude_inactive

    @exclude_inactive.setter
    def exclude_inactive(self, exclude_inactive: bool):
        """Sets the exclude_inactive of this CalculatedPullRequestMetrics.

        Repeats `PullRequestMetricsRequest.exclude_inactive`.

        :param exclude_inactive: The exclude_inactive of this CalculatedPullRequestMetrics.
        """
        self._exclude_inactive = exclude_inactive
