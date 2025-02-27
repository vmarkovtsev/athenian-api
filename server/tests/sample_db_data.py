import datetime
from itertools import chain
import json
from lzma import LZMAFile
import os
from pathlib import Path
from typing import Dict

from sqlalchemy import and_
from sqlalchemy.cprocessors import str_to_date, str_to_datetime
import sqlalchemy.orm
from sqlalchemy.sql.type_api import Variant

from athenian.api.controllers import invitation_controller
from athenian.api.controllers.invitation_controller import _generate_account_secret
from athenian.api.db import extract_registered_models
from athenian.api.models.metadata import __min_version__
from athenian.api.models.metadata.github import (
    Base as GithubBase,
    CheckRunByPR,
    NodeCommit,
    NodePullRequest,
    PullRequest,
    PushCommit,
    SchemaMigration,
    ShadowBase as ShadowGithubBase,
)
from athenian.api.models.metadata.jira import Base as JiraBase
from athenian.api.models.persistentdata.models import DeployedComponent, DeploymentNotification
from athenian.api.models.state.models import (
    Account,
    AccountFeature,
    AccountGitHubAccount,
    AccountJiraInstallation,
    Feature,
    FeatureComponent,
    Invitation,
    RepositorySet,
    UserAccount,
    WorkType,
)


def fill_metadata_session(session: sqlalchemy.orm.Session):
    models = {}
    tables = {**GithubBase.metadata.tables, **JiraBase.metadata.tables}
    for cls in chain(
        extract_registered_models(GithubBase).values(),
        extract_registered_models(JiraBase).values(),
        # shadow tables overwrite the original ones
        extract_registered_models(ShadowGithubBase).values(),
    ):
        table = getattr(cls, "__table__", None)
        if table is not None:
            models[table.fullname] = cls
    data_file = os.getenv("DB_DATA")
    if data_file is None:
        data_file = Path(__file__).with_name("test_data.sql.xz")
    else:
        data_file = Path(data_file)
    if data_file.suffix == ".xz":
        opener = lambda: LZMAFile(data_file)  # noqa:E731
    else:
        opener = lambda: open(data_file, "rb")  # noqa:E731
    with opener() as fin:
        stdin = False
        for line in fin:
            if not stdin and line.startswith(b"COPY "):
                stdin = True
                parts = line[5:].split(b" ")
                table = parts[0].decode()
                if table.startswith("public."):
                    table = table[7:]
                model = models[table]
                columns = {}
                for c in tables[table].columns:
                    if isinstance(c.type, Variant):
                        try:
                            pt = c.type.mapping.get("postgresql", c.type.impl).python_type
                        except NotImplementedError:
                            # HSTORE
                            pt = None
                            ctor = _parse_hstore
                    else:
                        pt = c.type.python_type
                    if pt is not None:
                        if pt is datetime.date:
                            ctor = str_to_date
                        elif pt is datetime.datetime:
                            ctor = str_to_datetime
                        elif pt is bool:
                            ctor = lambda x: x == "t" or x == "1"  # noqa:E731
                        elif issubclass(pt, (list, dict)):
                            ctor = lambda x: [s for s in x.strip("{}").split(",") if s]  # noqa
                        else:
                            ctor = lambda x: x  # noqa:E731
                    columns[c.name] = ctor
                keys = [p.strip(b'(),"').decode() for p in parts[1:-2]]
                name_map = {
                    getattr(model, k).name: k
                    for k in dir(model)
                    if not k.startswith("_") and hasattr(getattr(model, k), "name")
                }
                continue
            if stdin:
                if line == b"\\.\n":
                    stdin = False
                    session.flush()
                    continue
                kwargs = {}
                vals = line[:-1].split(b"\t")
                for k, p in zip(keys, vals):
                    p = p.replace(b"\\t", b"\t").replace(b"\\n", b"\n").decode()
                    if p == r"\N":
                        kwargs[name_map[k]] = None
                    else:
                        try:
                            kwargs[name_map[k]] = columns[k](p)
                        except Exception as e:
                            print("%s.%s" % (table, k), p)
                            for k, p in zip(keys, vals):
                                print(k, '"%s"' % p.decode())
                            raise e from None
                # FIXME(vmarkovtsev): remove these when the rest of the code is updated DEV-3537
                if table == "github.node_reviewrequestedevent":
                    kwargs["requested_reviewer_id"] = kwargs["requested_reviewer_id"] or 0
                for key, val in kwargs.items():
                    if key.endswith("_user_id") or key == "user_node_id":
                        kwargs[key] = val or 0
                session.add(model(**kwargs))
                if table == "github.api_pull_requests":
                    session.add(
                        NodePullRequest(
                            graph_id=kwargs["node_id"],
                            acc_id=kwargs["acc_id"],
                            title=kwargs["title"],
                            author_id=kwargs["user_node_id"],
                            merged=kwargs["merged"],
                            merged_at=kwargs["merged_at"],
                            merge_commit_id=kwargs["merge_commit_id"],
                            additions=kwargs["additions"],
                            deletions=kwargs["deletions"],
                            number=kwargs["number"],
                            repository_id=kwargs["repository_node_id"],
                            created_at=kwargs["created_at"],
                            closed_at=kwargs["closed_at"],
                        ),
                    )
                elif table == "github.api_push_commits":
                    session.add(
                        NodeCommit(
                            graph_id=kwargs["node_id"],
                            acc_id=kwargs["acc_id"],
                            oid=kwargs["sha"],
                            message=kwargs["message"],
                            repository_id=kwargs["repository_node_id"],
                            committed_date=kwargs["committed_date"],
                            pushed_date=kwargs["pushed_date"],
                            committer_user_id=kwargs["committer_user_id"],
                            committer_name=kwargs["committer_name"],
                            committer_email=kwargs["committer_email"],
                            author_user_id=kwargs["author_user_id"],
                            author_name=kwargs["author_name"],
                            author_email=kwargs["author_email"],
                            additions=kwargs["additions"],
                            deletions=kwargs["deletions"],
                        ),
                    )
                elif table == "github.api_check_runs":
                    del kwargs["committed_date_hack"]
                    del kwargs["pull_request_created_at"]
                    del kwargs["pull_request_closed_at"]
                    session.add(CheckRunByPR(**kwargs))
    session.add(SchemaMigration(version=__min_version__, dirty=False))
    session.flush()
    # append missed merge commit IDs to PRs
    commit_ids = {h: n for h, n in session.query(PushCommit.sha, PushCommit.node_id)}
    for pr in session.query(PullRequest).filter(PullRequest.merge_commit_sha.isnot(None)):
        pr.merge_commit_id = commit_ids[pr.merge_commit_sha]


def _parse_hstore(x: str) -> Dict[str, str]:
    return json.loads("{%s}" % x.strip("'").replace("=>", ":"))


def fill_state_session(session: sqlalchemy.orm.Session):
    expires = datetime.datetime(2030, 1, 1)
    salt, secret = _generate_account_secret(1, "secret")
    session.add(Account(secret_salt=salt, secret=secret, expires_at=expires))
    salt, secret = _generate_account_secret(2, "secret")
    session.add(Account(secret_salt=salt, secret=secret, expires_at=expires))
    salt, secret = _generate_account_secret(3, "secret")
    session.add(Account(secret_salt=salt, secret=secret, expires_at=expires))
    salt, secret = _generate_account_secret(invitation_controller.admin_backdoor, "secret")
    session.add(
        Account(
            id=invitation_controller.admin_backdoor,
            secret_salt=salt,
            secret=secret,
            expires_at=expires,
        ),
    )
    session.flush()
    session.add(AccountGitHubAccount(id=6366825, account_id=1))
    session.add(UserAccount(user_id="auth0|62a1ae88b6bba16c6dbc6870", account_id=1, is_admin=True))
    session.add(
        UserAccount(user_id="auth0|62a1ae88b6bba16c6dbc6870", account_id=2, is_admin=False),
    )
    session.add(UserAccount(user_id="auth0|5e1f6e2e8bfa520ea5290741", account_id=3, is_admin=True))
    session.add(
        UserAccount(user_id="auth0|5e1f6e2e8bfa520ea5290741", account_id=1, is_admin=False),
    )
    session.add(
        RepositorySet(
            name="all",
            owner_id=1,
            precomputed=os.getenv("PRECOMPUTED", "1") == "1",
            tracking_re=".*alpha",
            items=[["github.com/src-d/gitbase", 39652769], ["github.com/src-d/go-git", 40550]],
        ),
    )
    session.add(
        RepositorySet(
            name="all",
            owner_id=2,
            items=[
                ["github.com/src-d/hercules", 39652771],
                ["github.com/athenianco/athenian-api", 0],
            ],
        ),
    )
    session.add(
        RepositorySet(
            name="all",
            owner_id=3,
            items=[
                ["github.com/athenianco/athenian-webapp", 0],
                ["github.com/athenianco/athenian-api", 0],
            ],
        ),
    )
    session.add(Invitation(salt=777, account_id=3, created_by="auth0|5e1f6e2e8bfa520ea5290741"))
    session.add(
        Feature(
            id=1000,
            name="jira",
            component=FeatureComponent.webapp,
            enabled=True,
            default_parameters={"a": "b", "c": "d"},
        ),
    )
    session.add(
        Feature(
            id=1001,
            name="bare_value",
            component=FeatureComponent.webapp,
            enabled=True,
            default_parameters=365,
        ),
    )
    session.flush()
    for name in (Feature.USER_ORG_MEMBERSHIP_CHECK, Feature.GITHUB_LOGIN_ENABLED):
        feature = (
            session.query(Feature)
            .filter(
                and_(
                    Feature.name == name,
                    Feature.component == FeatureComponent.server,
                ),
            )
            .one_or_none()
        )
        if feature is None:
            session.add(Feature(name=name, component=FeatureComponent.server, enabled=True))
    session.add(AccountFeature(account_id=1, feature_id=1000, enabled=True, parameters={"a": "x"}))
    session.add(AccountFeature(account_id=1, feature_id=1001, enabled=True, parameters=28))
    session.add(AccountJiraInstallation(id=1, account_id=1))
    session.add(
        WorkType(
            account_id=1,
            name="Bug Fixing",
            color="FF0000",
            rules=[["pull_request/label_include", ["bug", "fix"]]],
        ),
    )


def fill_persistentdata_session(session: sqlalchemy.orm.Session):
    session.add(
        DeploymentNotification(
            account_id=1,
            name="Dummy deployment",
            conclusion="SUCCESS",
            environment="production",
            url=None,
            started_at=datetime.datetime(2019, 11, 1, 12, 0, tzinfo=datetime.timezone.utc),
            finished_at=datetime.datetime(2019, 11, 1, 12, 15, tzinfo=datetime.timezone.utc),
        ),
    )
    session.flush()
    session.add(
        DeployedComponent(
            account_id=1,
            deployment_name="Dummy deployment",
            repository_node_id=40550,
            reference="v4.13.1",
            resolved_commit_node_id=2755244,
        ),
    )
