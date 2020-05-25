from datetime import datetime, timezone

from sqlalchemy import ARRAY, CHAR, Column, func, Integer, LargeBinary, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import HSTORE

from athenian.api.models import create_base


Base = create_base()


class GitHubPullRequestTimes(Base):
    """
    Mined PullRequestTimes.

    Tricky columns:
        * `release_match`: the description of the release match strategy applied to this PR. \
                           Note that `pr_done_at` depends on that.
        * `pr_done_at`: PR closure timestamp if it is not merged or PR release timestamp if it is.
        * `HSTORE` a set of developers with which we can efficiently check an intersection.
        * `data`: pickle-d PullRequestTimes (may change in the future).
        * `format_version`: version of the `data` format. When the "future" happens, we will \
                            bump it.
    """

    __tablename__ = "github_pull_request_times"

    pr_node_id = Column(CHAR(32), primary_key=True)
    release_match = Column(Text(), primary_key=True)
    repository_full_name = Column(String(64 + 1 + 100), nullable=False)
    pr_created_at = Column(TIMESTAMP(timezone=True), nullable=False)
    pr_done_at = Column(TIMESTAMP(timezone=True))
    author = Column(CHAR(100))  # can be null, see @ghost
    merger = Column(CHAR(100))
    releaser = Column(CHAR(100))
    reviewers = Column(HSTORE(), nullable=False, server_default="")
    commenters = Column(HSTORE(), nullable=False, server_default="")
    commit_authors = Column(HSTORE(), nullable=False, server_default="")
    commit_committers = Column(HSTORE(), nullable=False, server_default="")
    activity_days = Column(ARRAY(TIMESTAMP(timezone=True)), nullable=False, server_default="{}")
    format_version = Column(Integer(), nullable=False, default=3, server_default="3")
    data = Column(LargeBinary(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        server_default=func.now(),
                        onupdate=lambda ctx: datetime.now(timezone.utc))
