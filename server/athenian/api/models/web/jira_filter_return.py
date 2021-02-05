from athenian.api.models.web import Enum, Model


class JIRAFilterReturn(Model, metaclass=Enum):
    """Requested chapter to return in `/filter/jira`."""

    EPICS = "epics"
    LABELS = "labels"
    ISSUE_TYPES = "issue_types"
    PRIORITIES = "priorities"
    STATUSES = "statuses"
    USERS = "users"
