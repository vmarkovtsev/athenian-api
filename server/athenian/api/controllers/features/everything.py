from datetime import datetime, timezone
from enum import Enum
from itertools import chain
from typing import Collection, Dict, Optional, Set, Tuple

import aiomcache
import databases
import pandas as pd
from sqlalchemy import and_, select

from athenian.api.async_utils import gather, read_sql_query
from athenian.api.controllers.features.github.pull_request_filter import PullRequestListMiner
from athenian.api.controllers.features.metric_calculator import df_from_structs
from athenian.api.controllers.miners.filters import JIRAFilter
from athenian.api.controllers.miners.github.branches import extract_branches
from athenian.api.controllers.miners.github.precomputed_prs import \
    load_merged_pull_request_facts_all, load_open_pull_request_facts_all, \
    load_precomputed_done_facts_all
from athenian.api.controllers.miners.github.release_mine import mine_releases
from athenian.api.controllers.miners.jira.issue import append_pr_jira_mapping
from athenian.api.controllers.prefixer import Prefixer, PrefixerPromise
from athenian.api.controllers.settings import ReleaseSettings
from athenian.api.models.metadata.github import PullRequest, Release
from athenian.precomputer.db.models import GitHubDonePullRequestFacts


class MineTopic(Enum):
    """Possible extracted item types."""

    prs = "prs"
    # developers = "developers"
    releases = "releases"
    # jira_epics = "jira_epics"
    # jira_issues = "jira_issues"


async def mine_all_prs(repos: Collection[str],
                       branches: pd.DataFrame,
                       default_branches: Dict[str, str],
                       settings: ReleaseSettings,
                       prefixer: PrefixerPromise,
                       account: int,
                       meta_ids: Tuple[int, ...],
                       mdb: databases.Database,
                       pdb: databases.Database,
                       rdb: databases.Database,
                       cache: Optional[aiomcache.Client]) -> pd.DataFrame:
    """Extract everything we know about pull requests."""
    ghdprf = GitHubDonePullRequestFacts
    done_facts, raw_done_rows = await load_precomputed_done_facts_all(
        repos, default_branches, settings, account, pdb,
        extra=[ghdprf.release_url, ghdprf.release_node_id])
    merged_facts = await load_merged_pull_request_facts_all(repos, done_facts, account, pdb)
    merged_node_ids = list(chain(done_facts.keys(), merged_facts.keys()))
    open_facts = await load_open_pull_request_facts_all(repos, merged_node_ids, account, pdb)
    del merged_node_ids
    facts = {**open_facts, **merged_facts, **done_facts}
    del open_facts
    del merged_facts
    del done_facts
    tasks = [
        read_sql_query(select([PullRequest]).where(and_(
            PullRequest.acc_id.in_(meta_ids),
            PullRequest.node_id.in_(facts),
        )), mdb, PullRequest, index=PullRequest.node_id.key),
        append_pr_jira_mapping(facts, meta_ids, mdb),
    ]
    df_prs, _ = await gather(*tasks, op="fetch raw data")
    df_facts = df_from_structs(facts.values())
    dummy = {ghdprf.release_url.key: None, ghdprf.release_node_id.key: None}
    for col in (ghdprf.release_url.key, ghdprf.release_node_id.key):
        df_facts[col] = [raw_done_rows.get(k, dummy)[col] for k in facts]
    del raw_done_rows
    df_facts[PullRequest.node_id.key] = list(facts)
    del facts
    df_facts.set_index(PullRequest.node_id.key, inplace=True)
    if not df_facts.empty:
        stage_timings = PullRequestListMiner.calc_stage_timings(
            df_facts, *PullRequestListMiner.create_stage_calcs())
        for stage, timings in stage_timings.items():
            df_facts[f"stage_time_{stage}"] = pd.to_timedelta(timings, unit="s")
        del stage_timings
    for col in df_prs:
        if col in df_facts:
            del df_facts[col]
    return df_prs.join(df_facts)


async def mine_all_releases(repos: Collection[str],
                            branches: pd.DataFrame,
                            default_branches: Dict[str, str],
                            settings: ReleaseSettings,
                            prefixer: PrefixerPromise,
                            account: int,
                            meta_ids: Tuple[int, ...],
                            mdb: databases.Database,
                            pdb: databases.Database,
                            rdb: databases.Database,
                            cache: Optional[aiomcache.Client]) -> pd.DataFrame:
    """Extract everything we know about releases."""
    releases = (await mine_releases(
        repos, {}, branches, default_branches, datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime.now(timezone.utc), JIRAFilter.empty(), settings, prefixer, account, meta_ids,
        mdb, pdb, rdb, cache, with_avatars=False, with_pr_titles=True))[0]
    df_gen = pd.DataFrame.from_records([r[0] for r in releases])
    df_facts = df_from_structs([r[1] for r in releases])
    del df_facts[Release.repository_full_name.key]
    result = df_gen.join(df_facts)
    result.set_index(Release.id.key, inplace=True)
    for col in ("commit_authors", "prs_user_login"):
        result[col] = [[s.decode() for s in subarr] for subarr in result[col].values]
    return result


miners = {
    MineTopic.prs: mine_all_prs,
    MineTopic.releases: mine_all_releases,
}


async def mine_everything(topics: Set[MineTopic],
                          settings: ReleaseSettings,
                          account: int,
                          meta_ids: Tuple[int, ...],
                          mdb: databases.Database,
                          pdb: databases.Database,
                          rdb: databases.Database,
                          cache: Optional[aiomcache.Client],
                          ) -> Dict[MineTopic, pd.DataFrame]:
    """Mine all the specified data topics."""
    repos = settings.native.keys()
    prefixer = Prefixer.schedule_load(meta_ids, mdb)
    branches, default_branches = await extract_branches(repos, meta_ids, mdb, cache)
    tasks = [miners[t](repos, branches, default_branches, settings, prefixer,
                       account, meta_ids, mdb, pdb, rdb, cache)
             for t in topics]
    results = await gather(*tasks, op="mine_everything")
    return dict(zip(topics, results))
