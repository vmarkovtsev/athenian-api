from datetime import timedelta
from typing import Optional

from athenian.api.controllers.features.github.pull_request import \
    PullRequestMedianMetricCalculator, register
from athenian.api.controllers.miners.github.pull_request import PullRequestTimes


@register("pr-wip-time")
class WorkInProgressTimeCalculator(PullRequestMedianMetricCalculator[timedelta]):
    """Time of work in progress metric."""

    may_have_negative_values = False

    def analyze(self, times: PullRequestTimes) -> Optional[timedelta]:
        """Do the actual state update. See the design document for more info."""
        if times.first_review_request:
            return times.first_review_request.best - times.work_began.best
        return None


@register("pr-review-time")
class ReviewTimeCalculator(PullRequestMedianMetricCalculator[timedelta]):
    """Time of the review process metric."""

    may_have_negative_values = False

    def analyze(self, times: PullRequestTimes) -> Optional[timedelta]:
        """Do the actual state update. See the design document for more info."""
        if times.first_review_request and times.closed:
            if times.approved:
                return times.approved.best - times.first_review_request.best
            elif times.last_review:
                return times.last_review.best - times.first_review_request.best
        return None


@register("pr-merging-time")
class MergeTimeCalculator(PullRequestMedianMetricCalculator[timedelta]):
    """Time to merge after finishing the review metric."""

    may_have_negative_values = False

    def analyze(self, times: PullRequestTimes) -> Optional[timedelta]:
        """Do the actual state update. See the design document for more info."""
        if times.approved and times.closed:
            # closed may mean either merged or not merged; both cases count though the latter
            # is embarrassing
            return times.closed.best - times.approved.best
        return None


@register("pr-release-time")
class ReleaseTimeCalculator(PullRequestMedianMetricCalculator[timedelta]):
    """Time to appear in a release after merging metric."""

    may_have_negative_values = False

    def analyze(self, times: PullRequestTimes) -> Optional[timedelta]:
        """Do the actual state update. See the design document for more info."""
        if times.merged.value is not None and times.released.value is not None:
            return times.released.value - times.merged.value
        return None


@register("pr-lead-time")
class LeadTimeCalculator(PullRequestMedianMetricCalculator[timedelta]):
    """Time to appear in a release since starting working on the PR."""

    may_have_negative_values = False

    def analyze(self, times: PullRequestTimes) -> Optional[timedelta]:
        """Do the actual state update. See the design document for more info."""
        if times.released.value is not None:
            return times.released.value - times.work_began.best
        return None
