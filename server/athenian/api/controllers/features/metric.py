from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

T = TypeVar("T", float, int, datetime)


@dataclass(frozen=True)
class Metric(Generic[T]):
    """Any statistic measurement bundled with the corresponding confidence interval."""

    exists: bool
    value: T
    confidence_min: T
    confidence_max: T

    def confidence_score(self) -> int:
        """Calculate the confidence score from 0 (garbage) to 100 (very confident)."""
        if not self.exists:
            return 0
        eps = min(100 * (self.confidence_max - self.confidence_min) / self.value, 100)
        return 100 - int(eps)
