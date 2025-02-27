from datetime import datetime, timedelta, timezone

import factory

from athenian.api.models.metadata.github import (
    Account,
    AccountRepository,
    Bot,
    FetchProgress,
    Team,
    TeamMember,
    User,
)
from athenian.api.models.metadata.jira import Issue, Project, User as JIRAUser

from .alchemy import SQLAlchemyModelFactory
from .common import DEFAULT_JIRA_ACCOUNT_ID, DEFAULT_MD_ACCOUNT_ID


class AccountRepositoryFactory(SQLAlchemyModelFactory):
    class Meta:
        model = AccountRepository

    acc_id = factory.Sequence(lambda n: n)
    repo_graph_id = factory.Sequence(lambda n: n)
    repo_full_name = factory.Sequence(lambda n: f"athenianco/proj-{n:02}")
    event_id = "event-00"
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class AccountFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Account

    id = factory.Sequence(lambda n: n)
    owner_id = factory.Sequence(lambda n: n)
    owner_login = factory.Sequence(lambda n: f"login-{n}")
    name = factory.Sequence(lambda n: f"name-{n}")
    install_url = factory.Sequence(
        lambda n: f"https://github.com/organizations/athenianco/settings/installations/{n}",
    )


class FetchProgressFactory(SQLAlchemyModelFactory):
    class Meta:
        model = FetchProgress

    acc_id = factory.Sequence(lambda n: n)
    event_id = factory.Sequence(lambda n: n)
    node_type = "Repository"
    nodes_total = 100
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc) - timedelta(days=3))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc) - timedelta(days=1))


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User

    acc_id = DEFAULT_MD_ACCOUNT_ID
    node_id = factory.Sequence(lambda n: n + 1)
    avatar_url = factory.LazyAttribute(lambda user: f"https://github.com/user-{user.node_id}.jpg")
    login = factory.LazyAttribute(lambda user: f"user-{user.node_id}")
    html_url = factory.LazyAttribute(lambda user: f"https://github.com/user-{user.node_id}")


class BotFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Bot

    acc_id = DEFAULT_MD_ACCOUNT_ID
    login = factory.LazyAttribute(lambda bot: f"bot-{bot.node_id}")


class TeamFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Team

    acc_id = DEFAULT_MD_ACCOUNT_ID
    node_id = factory.Sequence(lambda n: n + 1)
    organization_id = 40469
    name = factory.LazyAttribute(lambda team: f"team-{team.node_id}")


class TeamMemberFactory(SQLAlchemyModelFactory):
    class Meta:
        model = TeamMember

    acc_id = DEFAULT_MD_ACCOUNT_ID
    parent_id = factory.Sequence(lambda n: n + 1)
    child_id = factory.Sequence(lambda n: n + 2)


class JIRAProjectFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Project

    acc_id = factory.Sequence(lambda n: n + 1)
    id = factory.Sequence(lambda n: str(n + 1))
    key = factory.Sequence(lambda n: f"PRJ-{n + 1:03d}")
    name = factory.Sequence(lambda n: f"Project {n + 1:03d}")
    avatar_url = factory.Sequence(lambda n: "https://jira.com/proj-{n + 1}/avatar")
    is_deleted = False


class JIRAIssueFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Issue

    acc_id = factory.Sequence(lambda n: n + 1)
    id = factory.Sequence(lambda n: str(n + 1))
    project_id = factory.Sequence(lambda n: n + 1)
    key = factory.LazyAttribute(lambda issue: f"ISSUE-{issue.id}")
    title = factory.LazyAttribute(lambda issue: f"Issue n. {issue.id}")
    type = "Task"
    type_id = "1"
    labels = []
    epic_id = factory.Sequence(lambda n: str(n + 1000))
    created = factory.LazyFunction(lambda: datetime.now(timezone.utc) - timedelta(days=3))
    updated = factory.LazyFunction(lambda: datetime.now(timezone.utc) - timedelta(days=1))
    reporter_id = "reporter-1"
    reporter_display_name = "Reporter N. 1"
    comments_count = 0
    priority_id = "1"
    priority_name = "HIGH"
    status_id = "1"
    status = "todo"
    url = factory.LazyAttribute(lambda issue: f"https://jira.com/issue-{issue.id}")

    @factory.post_generation
    def athenian_epic_id(obj, create, extracted, **kwargs):
        # adding athenian_epic_id attr is required since explode_model() doesn't
        # work with aliased columns, i.e. epic_id = Column("athenian_epic_id", Text)
        obj.athenian_epic_id = obj.epic_id


class JIRAUserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = JIRAUser

    acc_id = DEFAULT_JIRA_ACCOUNT_ID
    id = factory.Sequence(lambda n: f"{n + 1}")
    type = "?"
    display_name = factory.LazyAttribute(lambda user: f"jira user {user.id}")
    avatar_url = factory.LazyAttribute(lambda user: f"https://jira.com/user-{user.id}.jpg")
