from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import chain
import logging
import operator
from typing import List, Optional, Set, Union

from aiohttp import web
import aiomcache
import databases
from dateutil.parser import parse as parse_datetime

from athenian.api.controllers.features.github.pull_request_filter import fetch_pull_requests, \
    filter_pull_requests
from athenian.api.controllers.miners.access_classes import access_classes
from athenian.api.controllers.miners.github.branches import extract_branches
from athenian.api.controllers.miners.github.commit import extract_commits, FilterCommitsProperty
from athenian.api.controllers.miners.github.contributors import mine_contributors
from athenian.api.controllers.miners.github.label import mine_labels
from athenian.api.controllers.miners.github.release import load_releases, mine_releases
from athenian.api.controllers.miners.github.repositories import mine_repositories
from athenian.api.controllers.miners.github.users import mine_user_avatars
from athenian.api.controllers.miners.types import ParticipationKind, Property, PullRequestListItem
from athenian.api.controllers.reposet import resolve_repos
from athenian.api.controllers.settings import Settings
from athenian.api.models.metadata import PREFIXES
from athenian.api.models.metadata.github import PushCommit, Release
from athenian.api.models.web import BadRequestError, Commit, CommitSignature, CommitsList, \
    ForbiddenError, InvalidRequestError
from athenian.api.models.web.developer_summary import DeveloperSummary
from athenian.api.models.web.developer_updates import DeveloperUpdates
from athenian.api.models.web.filter_commits_request import FilterCommitsRequest
from athenian.api.models.web.filter_contributors_request import FilterContributorsRequest
from athenian.api.models.web.filter_labels_request import FilterLabelsRequest
from athenian.api.models.web.filter_pull_requests_request import FilterPullRequestsRequest
from athenian.api.models.web.filtered_label import FilteredLabel
from athenian.api.models.web.filtered_release import FilteredRelease
from athenian.api.models.web.filtered_releases import FilteredReleases
from athenian.api.models.web.generic_filter_request import GenericFilterRequest
from athenian.api.models.web.get_pull_requests_request import GetPullRequestsRequest
from athenian.api.models.web.included_native_user import IncludedNativeUser
from athenian.api.models.web.included_native_users import IncludedNativeUsers
from athenian.api.models.web.pull_request import PullRequest as WebPullRequest
from athenian.api.models.web.pull_request_label import PullRequestLabel
from athenian.api.models.web.pull_request_participant import PullRequestParticipant
from athenian.api.models.web.pull_request_set import PullRequestSet
from athenian.api.models.web.stage_timings import StageTimings
from athenian.api.request import AthenianWebRequest
from athenian.api.response import model_response, ResponseError
from athenian.api.tracing import sentry_span


async def filter_contributors(request: AthenianWebRequest, body: dict) -> web.Response:
    """Find developers that made an action within the given timeframe."""
    try:
        filt = FilterContributorsRequest.from_dict(body)  # type: FilterContributorsRequest
    except ValueError as e:
        # for example, passing a date with day=32
        return ResponseError(InvalidRequestError("?", detail=str(e))).response
    repos = await _common_filter_preprocess(filt, request)
    users = await mine_contributors(
        repos, filt.date_from, filt.date_to, request.mdb, request.cache,
        as_roles=filt.as_)
    model = [
        DeveloperSummary(
            login=f"{PREFIXES['github']}{u['login']}", avatar=u["avatar_url"],
            name=u["name"], updates=DeveloperUpdates(**{
                k: v for k, v in u["stats"].items()
                # TODO(se7entyse7en): make `DeveloperUpdates` support all the stats we can get instead of doing this filtering. See also `mine_contributors`.  # noqa
                if k in DeveloperUpdates.openapi_types
            }),
        )
        for u in sorted(users, key=operator.itemgetter("login"))
    ]
    return model_response(model)


async def filter_repositories(request: AthenianWebRequest, body: dict) -> web.Response:
    """Find repositories that were updated within the given timeframe."""
    try:
        filt = GenericFilterRequest.from_dict(body)  # type: GenericFilterRequest
    except ValueError as e:
        # for example, passing a date with day=32
        return ResponseError(InvalidRequestError("?", detail=str(e))).response
    repos = await _common_filter_preprocess(filt, request)
    repos = await mine_repositories(
        repos, filt.date_from, filt.date_to, request.mdb, request.cache)
    return web.json_response(repos)


async def _common_filter_preprocess(filt: Union[GenericFilterRequest,
                                                FilterPullRequestsRequest,
                                                FilterCommitsRequest],
                                    request: AthenianWebRequest,
                                    strip_prefix=True) -> Set[str]:
    if filt.date_to < filt.date_from:
        raise ResponseError(InvalidRequestError(
            detail="date_from may not be greater than date_to",
            pointer=".date_from",
        ))
    filt.date_from = datetime.combine(filt.date_from, datetime.min.time(), tzinfo=timezone.utc)
    filt.date_to = datetime.combine(
        filt.date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    if filt.timezone is not None:
        tzoffset = timedelta(minutes=-filt.timezone)
        filt.date_from += tzoffset
        filt.date_to += tzoffset
    return await resolve_repos(
        filt.in_, filt.account, request.uid, request.native_uid,
        request.sdb, request.mdb, request.cache, request.app["slack"], strip_prefix=strip_prefix)


async def filter_prs(request: AthenianWebRequest, body: dict) -> web.Response:
    """List pull requests that satisfy the query."""
    try:
        filt = FilterPullRequestsRequest.from_dict(body)  # type: FilterPullRequestsRequest
    except ValueError as e:
        # for example, passing a date with day=32
        return ResponseError(InvalidRequestError("?", detail=str(e))).response
    repos = await _common_filter_preprocess(filt, request, strip_prefix=False)
    props = set(getattr(Property, p.upper()) for p in (filt.properties or []))
    if not props:
        props = set(Property)
    participants = {ParticipationKind[k.upper()]: {d.split("/", 1)[1] for d in v}
                    for k, v in (filt.with_ or {}).items() if v}
    settings = await Settings.from_request(request, filt.account).list_release_matches(repos)
    repos = {r.split("/", 1)[1] for r in repos}
    prs = await filter_pull_requests(
        props, filt.date_from, filt.date_to, repos, participants, set(filt.labels_include or []),
        filt.exclude_inactive, settings, request.mdb, request.pdb, request.cache)
    return await _build_github_prs_response(prs, request.mdb, request.cache)


def _web_pr_from_struct(pr: PullRequestListItem) -> WebPullRequest:
    props = vars(pr).copy()
    props["properties"] = sorted(p.name.lower() for p in pr.properties)
    props["stage_timings"] = StageTimings(**pr.stage_timings)
    participants = defaultdict(list)
    prefix = PREFIXES["github"]
    for pk, pids in sorted(pr.participants.items()):
        pkweb = pk.name.lower()
        for pid in pids:
            participants[prefix + pid].append(pkweb)
    props["participants"] = sorted(PullRequestParticipant(*p) for p in participants.items())
    if pr.labels is not None:
        props["labels"] = [PullRequestLabel(**label.__dict__) for label in pr.labels]
    return WebPullRequest(**props)


def _nan_to_none(val):
    if val != val:
        return None
    return val


async def filter_commits(request: AthenianWebRequest, body: dict) -> web.Response:
    """Find commits that match the specified query."""
    try:
        filt = FilterCommitsRequest.from_dict(body)
    except ValueError as e:
        # for example, passing a date with day=32
        return ResponseError(InvalidRequestError("?", detail=str(e))).response
    repos = await _common_filter_preprocess(filt, request)
    with_author = [s.split("/", 1)[1] for s in (filt.with_author or [])]
    with_committer = [s.split("/", 1)[1] for s in (filt.with_committer or [])]
    log = logging.getLogger("filter_commits")
    commits = await extract_commits(
        FilterCommitsProperty(filt.property), filt.date_from, filt.date_to, repos,
        with_author, with_committer, request.mdb, request.cache)
    model = CommitsList(data=[], include=IncludedNativeUsers(users={}))
    users = model.include.users
    utc = timezone.utc
    prefix = PREFIXES["github"]
    for commit in commits.itertuples():
        author_login = getattr(commit, PushCommit.author_login.key)
        committer_login = getattr(commit, PushCommit.committer_login.key)
        obj = Commit(
            repository=getattr(commit, PushCommit.repository_full_name.key),
            hash=getattr(commit, PushCommit.sha.key),
            message=getattr(commit, PushCommit.message.key),
            size_added=_nan_to_none(getattr(commit, PushCommit.additions.key)),
            size_removed=_nan_to_none(getattr(commit, PushCommit.deletions.key)),
            files_changed=_nan_to_none(getattr(commit, PushCommit.changed_files.key)),
            author=CommitSignature(
                login=(prefix + author_login) if author_login else None,
                name=getattr(commit, PushCommit.author_name.key),
                email=getattr(commit, PushCommit.author_email.key),
                timestamp=getattr(commit, PushCommit.authored_date.key).replace(tzinfo=utc),
            ),
            committer=CommitSignature(
                login=(prefix + committer_login) if committer_login else None,
                name=getattr(commit, PushCommit.committer_name.key),
                email=getattr(commit, PushCommit.committer_email.key),
                timestamp=getattr(commit, PushCommit.committed_date.key).replace(tzinfo=utc),
            ),
        )
        try:
            dt = parse_datetime(getattr(commit, PushCommit.author_date.key))
            obj.author.timezone = dt.tzinfo.utcoffset(dt).total_seconds() / 3600
        except ValueError:
            log.warning("Failed to parse the author timestamp of %s", obj.hash)
        try:
            dt = parse_datetime(getattr(commit, PushCommit.commit_date.key))
            obj.committer.timezone = dt.tzinfo.utcoffset(dt).total_seconds() / 3600
        except ValueError:
            log.warning("Failed to parse the committer timestamp of %s", obj.hash)
        if obj.author.login and obj.author.login not in users:
            users[obj.author.login] = IncludedNativeUser(
                avatar=getattr(commit, PushCommit.author_avatar_url.key))
        if obj.committer.login and obj.committer.login not in users:
            users[obj.committer.login] = IncludedNativeUser(
                getattr(commit, PushCommit.committer_avatar_url.key))
        model.data.append(obj)
    return model_response(model)


async def filter_releases(request: AthenianWebRequest, body: dict) -> web.Response:
    """Find releases that were published in the given time fram in the given repositories."""
    try:
        filt = GenericFilterRequest.from_dict(body)
    except ValueError as e:
        # for example, passing a date with day=32
        return ResponseError(InvalidRequestError("?", detail=str(e))).response
    repos = await _common_filter_preprocess(filt, request, strip_prefix=False)
    settings = await Settings.from_request(request, filt.account).list_release_matches(repos)
    repos = [r.split("/", 1)[1] for r in repos]
    branches, default_branches = await extract_branches(repos, request.mdb, request.cache)
    releases, _ = await load_releases(
        repos, branches, default_branches, filt.date_from - timedelta(days=365), filt.date_to,
        settings, request.mdb, request.pdb, request.cache, index=Release.id.key)
    stats, avatars = await mine_releases(
        releases, filt.date_from, request.mdb, request.pdb, request.cache)
    data = [FilteredRelease(**items) for _, items in stats.iterrows()]
    model = FilteredReleases(data=data, include=IncludedNativeUsers(users={
        u: IncludedNativeUser(avatar=a) for u, a in avatars}))
    return model_response(model)


async def get_prs(request: AthenianWebRequest, body: dict) -> web.Response:
    """List pull requests by repository and number."""
    body = GetPullRequestsRequest.from_dict(body)  # type: GetPullRequestsRequest
    repos = {}
    for p in body.prs:
        repos.setdefault(p.repository, set()).update(p.numbers)
    checkers = {}
    repos_by_service = {}
    reverse_prefixes = {v: k for k, v in PREFIXES.items()}
    async with request.sdb.connection() as sdb_conn:
        async with request.mdb.connection() as mdb_conn:
            for repo in repos:
                for prefix, service in reverse_prefixes.items():  # noqa: B007
                    if repo.startswith(prefix):
                        break
                else:
                    raise ResponseError(BadRequestError(
                        detail="Repository %s is unsupported" % repo))
                try:
                    checker = checkers[service]
                except KeyError:
                    checker = checkers[service] = access_classes[service](
                        body.account, sdb_conn, mdb_conn, request.cache)
                    await checker.load()
                repo = repo[len(prefix):]
                denied = await checker.check({repo})
                if denied:
                    raise ResponseError(ForbiddenError(
                        detail="Account %d is access denied to repo %s" % (body.account, repo)))
                repos_by_service.setdefault(service, []).append(repo)
    try:
        github_repos = {r: repos[PREFIXES["github"] + r] for r in repos_by_service["github"]}
    except KeyError:
        return model_response(PullRequestSet())
    settings = await Settings.from_request(request, body.account).list_release_matches(repos)
    prs = await fetch_pull_requests(
        github_repos, settings, request.mdb, request.pdb, request.cache)
    return await _build_github_prs_response(prs, request.mdb, request.cache)


@sentry_span
async def _build_github_prs_response(prs: List[PullRequestListItem],
                                     mdb: databases.Database,
                                     cache: Optional[aiomcache.Client]) -> web.Response:
    web_prs = sorted(_web_pr_from_struct(pr) for pr in prs)
    users = set(chain.from_iterable(chain.from_iterable(pr.participants.values()) for pr in prs))
    avatars = await mine_user_avatars(users, mdb, cache)
    prefix = PREFIXES["github"]
    model = PullRequestSet(include=IncludedNativeUsers(users={
        prefix + login: IncludedNativeUser(avatar=avatar) for login, avatar in avatars
    }), data=web_prs)
    return model_response(model)


async def filter_labels(request: AthenianWebRequest, body: dict) -> web.Response:
    """Find labels used in the given repositories."""
    body = FilterLabelsRequest.from_dict(body)  # type: FilterLabelsRequest
    repos = await resolve_repos(body.repositories, body.account, request.uid, request.native_uid,
                                request.sdb, request.mdb, request.cache, request.app["slack"])
    labels = await mine_labels(repos, request.mdb, request.cache)
    labels = [FilteredLabel(**label.__dict__) for label in labels]
    return model_response(labels)
