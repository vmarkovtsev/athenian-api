import argparse
import asyncio
from collections import defaultdict
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from itertools import chain
import logging
import os
import sys
import traceback
from typing import Collection, Optional, Set, Tuple

import aiomcache
from flogging import flogging
import numpy as np
import sentry_sdk
from slack_sdk.web.async_client import AsyncWebClient as SlackWebClient
from sqlalchemy import and_, desc, func, insert, select, update
from tqdm import tqdm

from athenian.api.__main__ import check_schema_versions, create_memcached, create_slack, \
    setup_context
from athenian.api.async_utils import gather
from athenian.api.cache import CACHE_VAR_NAME, setup_cache_metrics
from athenian.api.controllers.account import copy_teams_as_needed, \
    generate_jira_invitation_link, get_metadata_account_ids, get_metadata_account_ids_or_empty
from athenian.api.controllers.events_controller import resolve_deployed_component_references
from athenian.api.controllers.features.entries import MetricEntriesCalculator
from athenian.api.controllers.jira import match_jira_identities
from athenian.api.controllers.miners.filters import JIRAFilter, LabelFilter
from athenian.api.controllers.miners.github.bots import bots as fetch_bots
from athenian.api.controllers.miners.github.branches import BranchMiner
from athenian.api.controllers.miners.github.contributors import mine_contributors
from athenian.api.controllers.miners.github.dag_accelerated import searchsorted_inrange
from athenian.api.controllers.miners.github.deployment import mine_deployments
from athenian.api.controllers.miners.github.precomputed_prs import \
    delete_force_push_dropped_prs
from athenian.api.controllers.miners.github.release_load import ReleaseLoader
from athenian.api.controllers.miners.github.release_mine import discover_first_releases, \
    hide_first_releases, mine_releases
from athenian.api.controllers.miners.types import PullRequestFacts
from athenian.api.controllers.prefixer import Prefixer
from athenian.api.controllers.reposet import load_account_state, refresh_repository_names
from athenian.api.controllers.settings import ReleaseMatch, Settings
import athenian.api.db
from athenian.api.db import Database, measure_db_overhead_and_retry
from athenian.api.defer import enable_defer, wait_deferred
from athenian.api.faster_pandas import patch_pandas
from athenian.api.models.metadata import dereference_schemas as dereference_metadata_schemas
from athenian.api.models.metadata.github import Account as GitHubAccount, NodePullRequest, \
    PullRequestLabel, User
from athenian.api.models.persistentdata import \
    dereference_schemas as dereference_persistentdata_schemas
from athenian.api.models.precomputed.models import GitHubDonePullRequestFacts, \
    GitHubMergedPullRequestFacts
from athenian.api.models.state.models import Account, RepositorySet, Team, UserAccount
from athenian.api.prometheus import PROMETHEUS_REGISTRY_VAR_NAME
from athenian.precomputer.db import dereference_schemas as dereference_precomputed_schemas


def _parse_args():
    parser = argparse.ArgumentParser()
    flogging.add_logging_args(parser)
    parser.add_argument("--metadata-db", required=True,
                        help="Metadata DB endpoint, e.g. postgresql://0.0.0.0:5432/metadata")
    parser.add_argument("--precomputed-db", required=True,
                        help="Precomputed DB endpoint, e.g. postgresql://0.0.0.0:5432/precomputed")
    parser.add_argument("--state-db", required=True,
                        help="State DB endpoint, e.g. postgresql://0.0.0.0:5432/state")
    parser.add_argument("--persistentdata-db", required=True,
                        help="Persistentdata DB endpoint, e.g. "
                             "postgresql://0.0.0.0:5432/persistentdata")
    parser.add_argument("--memcached", required=True,
                        help="memcached address, e.g. 0.0.0.0:11211")
    return parser.parse_args()


async def _connect_to_dbs(args: argparse.Namespace,
                          ) -> Tuple[Database, Database,
                                     Database, Database]:
    sdb = measure_db_overhead_and_retry(Database(args.state_db))
    mdb = measure_db_overhead_and_retry(Database(args.metadata_db))
    pdb = measure_db_overhead_and_retry(Database(args.precomputed_db))
    rdb = measure_db_overhead_and_retry(Database(args.persistentdata_db))
    await gather(sdb.connect(), mdb.connect(), pdb.connect(), rdb.connect())
    pdb.metrics = {
        "hits": ContextVar("pdb_hits", default=defaultdict(int)),
        "misses": ContextVar("pdb_misses", default=defaultdict(int)),
    }
    if mdb.url.dialect == "sqlite":
        dereference_metadata_schemas()
    if rdb.url.dialect == "sqlite":
        dereference_persistentdata_schemas()
    if pdb.url.dialect == "sqlite":
        dereference_precomputed_schemas()
    return sdb, mdb, pdb, rdb


def main():
    """Go away linter."""
    athenian.api.db._testing = True
    patch_pandas()

    log = logging.getLogger("heater")
    args = _parse_args()
    setup_context(log)
    with sentry_sdk.Hub.current.configure_scope() as scope:
        scope.transaction = "heater"
    if not check_schema_versions(args.metadata_db,
                                 args.state_db,
                                 args.precomputed_db,
                                 args.persistentdata_db,
                                 log):
        return 1
    slack = create_slack(log)
    time_to = datetime.combine(date.today() + timedelta(days=1),
                               datetime.min.time(),
                               tzinfo=timezone.utc)
    no_time_from = datetime(1970, 1, 1, tzinfo=timezone.utc)
    time_from = (time_to - timedelta(days=365 * 2)) if not os.getenv("CI") else no_time_from
    return_code = 0
    successful_accounts = set()
    failed_accounts = set()

    async def async_run():
        enable_defer(False)
        cache = create_memcached(args.memcached, log)
        setup_cache_metrics({CACHE_VAR_NAME: cache, PROMETHEUS_REGISTRY_VAR_NAME: None})
        for v in cache.metrics["context"].values():
            v.set(defaultdict(int))
        sdb, mdb, pdb, rdb = await _connect_to_dbs(args)

        nonlocal return_code
        return_code = await sync_labels(log, mdb, pdb)
        log.info("Resolving deployed references")
        await gather(
            resolve_deployed_component_references(sdb, mdb, rdb, cache),
            notify_almost_expired_accounts(sdb, mdb, slack, log, cache),
        )

        account_progress_settings = {}
        accounts = [r[0] for r in await sdb.fetch_all(
            select([Account.id])
            .where(Account.expires_at > datetime.now(timezone.utc))
            .order_by(desc(Account.created_at)))]
        log.info("Checking progress of %d accounts", len(accounts))
        for account in tqdm(accounts):
            state = await load_account_state(account, sdb, mdb, cache, slack, log=log)
            if state is not None:
                account_progress_settings[account] = state
        reposets = await sdb.fetch_all(
            select([RepositorySet])
            .where(and_(RepositorySet.name == RepositorySet.ALL,
                        RepositorySet.owner_id.in_(accounts))))
        reposets = [RepositorySet(**r) for r in reposets]
        log.info("Heating %d reposets", len(reposets))
        for reposet in tqdm(reposets):
            try:
                progress = account_progress_settings[reposet.owner_id]
            except KeyError:
                log.warning("Skipped account %d / reposet %d because the progress does not exist",
                            reposet.owner_id, reposet.id)
                continue
            if progress.finished_date is None:
                log.warning("Skipped account %d / reposet %d because the progress is not 100%%",
                            reposet.owner_id, reposet.id)
                continue
            try:
                meta_ids = await get_metadata_account_ids(reposet.owner_id, sdb, cache)
                prefixer, bots, new_items = await gather(
                    Prefixer.load(meta_ids, mdb, cache),
                    fetch_bots(reposet.owner_id, mdb, sdb, None),
                    refresh_repository_names(reposet.owner_id, meta_ids, sdb, mdb),
                )
            except Exception as e:
                log.error("prolog %d: %s: %s", reposet.owner_id, type(e).__name__, e)
                sentry_sdk.capture_exception(e)
                return_code = 1
                failed_accounts.add(reposet.owner_id)
                continue
            reposet.items = new_items
            log.info("Loaded %d bots", len(bots))
            if not reposet.precomputed:
                log.info("Considering account %d as brand new, creating the teams",
                         reposet.owner_id)
                try:
                    num_teams, num_bots = await create_teams(
                        reposet.owner_id, meta_ids, reposet.items, bots, prefixer,
                        sdb, mdb, pdb, rdb, cache)
                except Exception as e:
                    log.warning("teams %d: %s: %s", reposet.owner_id, type(e).__name__, e)
                    sentry_sdk.capture_exception(e)
                    return_code = 1
                    failed_accounts.add(reposet.owner_id)
                    num_teams = num_bots = 0
                    # no continue
            try:
                await match_jira_identities(reposet.owner_id, meta_ids, sdb, mdb, slack, cache)
            except Exception as e:
                log.warning("match_jira_identities %d: %s: %s",
                            reposet.owner_id, type(e).__name__, e)
                sentry_sdk.capture_exception(e)
                return_code = 1
                failed_accounts.add(reposet.owner_id)
                # no continue
            log.info("Heating reposet %d of account %d (%d repos)",
                     reposet.id, reposet.owner_id, len(reposet.items))
            try:
                settings = Settings.from_account(reposet.owner_id, sdb, mdb, cache, None)
                repos = {r.split("/", 1)[1] for r in reposet.items}
                logical_settings, release_settings, (branches, default_branches) = await gather(
                    settings.list_logical_repositories(prefixer, reposet.items),
                    settings.list_release_matches(reposet.items),
                    BranchMiner.extract_branches(repos, prefixer, meta_ids, mdb, None),
                )
                branches_count = len(branches)

                log.info("Mining the releases")
                releases, _, matches, _ = await mine_releases(
                    repos, {}, branches, default_branches, no_time_from, time_to,
                    LabelFilter.empty(), JIRAFilter.empty(), release_settings, logical_settings,
                    prefixer, reposet.owner_id, meta_ids, mdb, pdb, rdb, None,
                    force_fresh=True, with_pr_titles=False, with_deployments=False)
                releases_by_tag = sum(
                    1 for r in releases if r[1].matched_by == ReleaseMatch.tag)
                releases_by_branch = sum(
                    1 for r in releases if r[1].matched_by == ReleaseMatch.branch)
                releases_count = len(releases)
                ignored_first_releases, ignored_released_prs = discover_first_releases(releases)
                del releases
                release_settings = ReleaseLoader.disambiguate_release_settings(
                    release_settings, matches)
                if reposet.precomputed:
                    log.info("Scanning for force push dropped PRs")
                    await delete_force_push_dropped_prs(
                        repos, branches, reposet.owner_id, meta_ids, mdb, pdb, None)
                log.info("Extracting PR facts")
                facts = await MetricEntriesCalculator(
                    reposet.owner_id,
                    meta_ids,
                    0,
                    mdb,
                    pdb,
                    rdb,
                    None,  # yes, disable the cache
                ).calc_pull_request_facts_github(
                    time_from,
                    time_to,
                    repos,
                    {},
                    LabelFilter.empty(),
                    JIRAFilter.empty(),
                    False,
                    bots,
                    release_settings,
                    logical_settings,
                    prefixer,
                    True,
                    False,
                    branches=branches,
                    default_branches=default_branches,
                )
                if not reposet.precomputed and slack is not None:
                    prs = len(facts)
                    prs_done = facts[PullRequestFacts.f.done].sum()
                    prs_merged = (
                        facts[PullRequestFacts.f.merged].notnull()
                        & ~facts[PullRequestFacts.f.done]
                    ).sum()
                    prs_open = facts[PullRequestFacts.f.closed].isnull().sum()
                del facts  # free some memory
                await wait_deferred()
                await hide_first_releases(
                    ignored_first_releases, ignored_released_prs, default_branches,
                    release_settings, account, pdb)
                ignored_releases_count = len(ignored_first_releases)
                del ignored_first_releases, ignored_released_prs
                log.info("Mining deployments")
                await mine_deployments(
                    repos, {}, no_time_from, time_to, [], [], {}, {}, LabelFilter.empty(),
                    JIRAFilter.empty(), release_settings, logical_settings,
                    branches, default_branches, prefixer, reposet.owner_id, meta_ids,
                    mdb, pdb, rdb, None)  # yes, disable the cache
                if not reposet.precomputed:
                    if slack is not None:
                        jira_link = await generate_jira_invitation_link(reposet.owner_id, sdb)
                        await slack.post_install(
                            "precomputed_account.jinja2",
                            account=reposet.owner_id,
                            prefixes={r.split("/", 2)[1] for r in reposet.items},
                            prs=prs,
                            prs_done=prs_done,
                            prs_merged=prs_merged,
                            prs_open=prs_open,
                            releases=releases_count,
                            ignored_first_releases=ignored_releases_count,
                            releases_by_tag=releases_by_tag,
                            releases_by_branch=releases_by_branch,
                            branches=branches_count,
                            repositories=len(repos),
                            bots_team_name=Team.BOTS,
                            bots=num_bots,
                            teams=num_teams,
                            jira_link=jira_link)
            except Exception as e:
                log.warning("reposet %d: %s: %s\n%s", reposet.id, type(e).__name__, e,
                            "".join(traceback.format_exception(*sys.exc_info())[:-1]))
                sentry_sdk.capture_exception(e)
                return_code = 1
                failed_accounts.add(reposet.owner_id)
            else:
                if not reposet.precomputed:
                    await sdb.execute(
                        update(RepositorySet)
                        .where(RepositorySet.id == reposet.id)
                        .values({RepositorySet.precomputed: True,
                                 RepositorySet.updates_count: RepositorySet.updates_count,
                                 RepositorySet.updated_at: datetime.now(timezone.utc)}))
            finally:
                await wait_deferred()
            successful_accounts.add(reposet.owner_id)

    async def sentry_wrapper():
        nonlocal return_code
        try:
            return await async_run()
        except Exception as e:
            log.warning("unhandled error: %s: %s\n%s", type(e).__name__, e, traceback.format_exc())
            sentry_sdk.capture_exception(e)
            return_code = 1

    asyncio.run(sentry_wrapper())
    log.info("Successful accounts: %d", len(successful_accounts))
    log.info("Failed accounts: %s", sorted(failed_accounts))
    return return_code


async def notify_almost_expired_accounts(sdb: Database,
                                         mdb: Database,
                                         slack: Optional[SlackWebClient],
                                         log: logging.Logger,
                                         cache: Optional[aiomcache.Client],
                                         ) -> None:
    """Find accounts that will expire in 24h and report them on Slack."""
    right = datetime.now(timezone.utc) + timedelta(days=1)
    left = right - timedelta(hours=1)
    accounts = dict(await sdb.fetch_all(
        select([Account.id, Account.expires_at])
        .where(Account.expires_at.between(left, right))))
    if not accounts:
        return
    log.info("Notifying about almost expired accounts: %s", sorted(accounts))
    user_rows, *meta_ids = await gather(
        sdb.fetch_all(
            select([UserAccount.account_id, UserAccount.user_id])
            .where(and_(UserAccount.account_id.in_(accounts),
                        UserAccount.is_admin)),
        ),
        *(get_metadata_account_ids_or_empty(acc, sdb, cache) for acc in accounts),
    )
    users = dict(user_rows)
    name_rows = await mdb.fetch_all(
        select([GitHubAccount.id, GitHubAccount.name])
        .where(GitHubAccount.id.in_(chain.from_iterable(meta_ids))))
    names = dict(name_rows)
    names = {acc: ", ".join(names[i] for i in m) for acc, m in zip(accounts, meta_ids)}
    tasks = [
        slack.post_account("almost_expired.jinja2",
                           account=acc,
                           name=names[acc],
                           user=users[acc],
                           expires=expires)
        for acc, expires in accounts.items()
    ]
    await gather(*tasks)


async def create_teams(account: int,
                       meta_ids: Tuple[int, ...],
                       repos: Collection[str],
                       all_bots: Set[str],
                       prefixer: Prefixer,
                       sdb: Database,
                       mdb: Database,
                       pdb: Database,
                       rdb: Database,
                       cache: Optional[aiomcache.Client]) -> Tuple[int, int]:
    """Copy the existing teams from GitHub and create a new team with all the involved bots \
    for the specified account.

    :return: Number of copied teams and the number of noticed bots.
    """
    _, num_teams = await copy_teams_as_needed(account, meta_ids, sdb, mdb, cache)
    bot_team = await sdb.fetch_one(select([Team.id, Team.members])
                                   .where(and_(Team.name == Team.BOTS,
                                               Team.owner_id == account)))
    if bot_team is not None:
        return num_teams, len(bot_team[Team.members.name])
    settings = Settings.from_account(account, sdb, mdb, None, None)
    release_settings, logical_settings = await gather(
        settings.list_release_matches(repos),
        settings.list_logical_repositories(prefixer, repos),
    )
    contributors = await mine_contributors(
        {r.split("/", 1)[1] for r in repos}, None, None, False, [],
        release_settings, logical_settings, prefixer, account, meta_ids, mdb, pdb, rdb, None,
        force_fresh_releases=True)
    if bots := {u[User.login.name] for u in contributors}.intersection(all_bots):
        bots = prefixer.prefix_user_logins(bots)
        await sdb.execute(insert(Team).values(
            Team(id=account, name=Team.BOTS, owner_id=account, members=sorted(bots))
            .create_defaults().explode()))
    return num_teams, len(bots)


async def sync_labels(log: logging.Logger, mdb: Database, pdb: Database) -> int:
    """Update the labels in `github.{done,merged}_pull_request_facts`."""
    log.info("Syncing labels")
    tasks = []
    all_prs = await mdb.fetch_all(select([NodePullRequest.id, NodePullRequest.acc_id]))
    log.info("There are %d PRs in mdb", len(all_prs))
    all_node_ids = np.fromiter((pr[0] for pr in all_prs), int, len(all_prs))
    all_accounts = np.fromiter((pr[1] for pr in all_prs), np.uint32, len(all_prs))
    del all_prs
    order = np.argsort(all_node_ids)
    all_node_ids = all_node_ids[order]
    all_accounts = all_accounts[order]
    del order
    all_pr_times = await pdb.fetch_all(
        select([GitHubDonePullRequestFacts.pr_node_id, GitHubDonePullRequestFacts.labels]))
    all_merged = await pdb.fetch_all(
        select([GitHubMergedPullRequestFacts.pr_node_id, GitHubMergedPullRequestFacts.labels]))
    unique_prs = np.unique(np.array([pr[0] for pr in chain(all_pr_times, all_merged)]))
    found_account_indexes = searchsorted_inrange(all_node_ids, unique_prs)
    found_mask = all_node_ids[found_account_indexes] == unique_prs
    unique_prs = unique_prs[found_mask]
    unique_pr_acc_ids = all_accounts[found_account_indexes[found_mask]]
    del found_mask
    del found_account_indexes
    del all_node_ids
    del all_accounts
    if (prs_count := len(unique_prs)) == 0:
        return 0
    log.info("Querying labels in %d PRs", prs_count)
    order = np.argsort(unique_pr_acc_ids)
    unique_prs = unique_prs[order]
    unique_pr_acc_ids = unique_pr_acc_ids[order]
    del order
    unique_acc_ids, acc_id_counts = np.unique(unique_pr_acc_ids, return_counts=True)
    del unique_pr_acc_ids
    node_id_by_acc_id = np.split(unique_prs, np.cumsum(acc_id_counts))
    del unique_prs
    del acc_id_counts
    for acc_id, node_ids in zip(unique_acc_ids, node_id_by_acc_id):
        tasks.append(mdb.fetch_all(
            select([PullRequestLabel.pull_request_node_id, func.lower(PullRequestLabel.name)])
            .where(and_(PullRequestLabel.pull_request_node_id.in_(node_ids),
                        PullRequestLabel.acc_id == int(acc_id)))))
    del unique_acc_ids
    del node_id_by_acc_id
    try:
        task_results = await gather(*tasks)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        log.warning("%s: %s", type(e).__name__, e)
        return 1
    actual_labels = defaultdict(dict)
    for row in chain.from_iterable(task_results):
        actual_labels[row[0]][row[1]] = ""
    log.info("Loaded labels for %d PRs", len(actual_labels))
    tasks = []
    for rows, model in ((all_pr_times, GitHubDonePullRequestFacts),
                        (all_merged, GitHubMergedPullRequestFacts)):
        for row in rows:
            assert isinstance(row[1], dict)
            if (pr_labels := actual_labels.get(row[0], {})) != row[1]:
                tasks.append(pdb.execute(
                    update(model)
                    .where(model.pr_node_id == row[0])
                    .values({model.labels: pr_labels,
                             model.updated_at: datetime.now(timezone.utc)})))
    if not tasks:
        return 0
    log.info("Updating %d records", len(tasks))
    while tasks:
        batch, tasks = tasks[:1000], tasks[1000:]
        try:
            await gather(*batch)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            log.warning("%s: %s", type(e).__name__, e)
            return 1
    return 0


if __name__ == "__main__":
    exit(main())
