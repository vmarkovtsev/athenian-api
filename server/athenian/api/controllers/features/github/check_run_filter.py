from datetime import date, datetime, timedelta, timezone
import pickle
from typing import Collection, List, Optional, Sequence, Tuple
import warnings

import aiomcache
from dateutil.rrule import MONTHLY, rrule
import numpy as np

from athenian.api.cache import cached
from athenian.api.controllers.miners.filters import JIRAFilter
from athenian.api.controllers.miners.github.check_run import mine_check_runs
from athenian.api.controllers.miners.github.pull_request import PullRequestMiner
from athenian.api.controllers.miners.types import CodeCheckRunListItem, CodeCheckRunListStats
from athenian.api.models.metadata.github import CheckRun
from athenian.api.tracing import sentry_span
from athenian.api.typing_utils import DatabaseLike


@sentry_span
@cached(
    exptime=PullRequestMiner.CACHE_TTL,
    serialize=pickle.dumps,
    deserialize=pickle.loads,
    key=lambda time_from, time_to, repositories, pushers, jira, **_:  # noqa
    (
        time_from.timestamp(), time_to.timestamp(),
        ",".join(sorted(repositories)),
        ",".join(sorted(pushers)),
        jira,
    ),
)
async def filter_check_runs(time_from: datetime,
                            time_to: datetime,
                            repositories: Collection[str],
                            pushers: Collection[str],
                            jira: JIRAFilter,
                            quantiles: Sequence[float],
                            meta_ids: Tuple[int, ...],
                            mdb: DatabaseLike,
                            cache: Optional[aiomcache.Client],
                            ) -> Tuple[List[date], List[CodeCheckRunListItem]]:
    """
    Gather information about code check runs according to the filters.

    :param time_from: Check runs must launch beginning from this time.
    :param time_to: Check runs must launch ending with this time.
    :param repositories: Check runs must belong to these repositories.
    :param pushers: Check runs must be triggered by these developers.
    :param jira: PR -> JIRA filters. This effectively makes "total" and "prs" stats the same.
    :param quantiles: Quantiles apply to the execution time distribution before calculating \
                      the means.
    :param meta_ids: Metadata account IDs.
    :param mdb: Metadata DB instance.
    :param cache: Optional memcached client.
    :return: 1. timeline - the X axis of all the charts. \
             2. list of the mined check run type's information and statistics.
    """
    df_check_runs = await mine_check_runs(
        time_from, time_to, repositories, pushers, jira, meta_ids, mdb, cache)
    timeline = _build_timeline(time_from, time_to)
    timeline_dates = [d.date() for d in timeline.tolist()]
    if df_check_runs.empty:
        return timeline_dates, []
    suite_statuses = df_check_runs[CheckRun.check_suite_status.key].values.astype("S")
    completed = np.nonzero(np.in1d(suite_statuses, [b"COMPLETED", b"SUCCESS", b"FAILURE"]))[0]
    df_check_runs = df_check_runs.take(completed)
    del suite_statuses, completed
    df_check_runs.sort_values(CheckRun.started_at.key, inplace=True, ascending=False)
    repocol = df_check_runs[CheckRun.repository_full_name.key].values.astype("S")
    crnamecol = df_check_runs[CheckRun.name.key].values.astype("S")
    group_keys = np.char.add(np.char.add(repocol, b"|"), crnamecol)
    unique_repo_crnames, first_encounters, inverse_cr_map, repo_crnames_counts = np.unique(
        group_keys, return_counts=True, return_index=True, return_inverse=True)
    unique_repo_crnames = np.char.partition(unique_repo_crnames, b"|").astype("U")
    started_ats = df_check_runs[CheckRun.started_at.key].values
    last_execution_times = started_ats[first_encounters].astype("datetime64[s]")
    last_execution_urls = df_check_runs[CheckRun.url.key].values[first_encounters]

    suitecol = df_check_runs[CheckRun.check_suite_node_id.key].values.astype("S")
    unique_suites, run_counts = np.unique(suitecol, return_counts=True)
    suite_blocks = np.array(np.split(np.argsort(suitecol), np.cumsum(run_counts)[:-1]))
    unique_run_counts, back_indexes, group_counts = np.unique(
        run_counts, return_inverse=True, return_counts=True)
    run_counts_order = np.argsort(back_indexes)
    ordered_indexes = np.concatenate(suite_blocks[run_counts_order])
    suite_size_map = np.zeros(len(df_check_runs), dtype=int)
    suite_size_map[ordered_indexes] = np.repeat(
        unique_run_counts, group_counts * unique_run_counts)

    no_pr_mask = df_check_runs[CheckRun.pull_request_node_id.key].isnull().values.astype(bool)
    prs_inverse_cr_map = inverse_cr_map.copy()
    prs_inverse_cr_map[no_pr_mask] = -1

    statuscol = df_check_runs[CheckRun.status.key].values.astype("S")
    conclusioncol = df_check_runs[CheckRun.conclusion.key].values.astype("S")
    success_mask = (statuscol == b"SUCCESS") | (conclusioncol == b"SUCCESS")
    skips_mask = conclusioncol == b"NEUTRAL"
    success_or_skipped_mask = success_mask | skips_mask
    failure_mask = (statuscol == b"FAILURE") | (statuscol == b"ERROR") | \
        (conclusioncol == b"FAILURE") | (conclusioncol == b"STALE")
    commitscol = df_check_runs[CheckRun.commit_node_id.key].values.astype("S")

    started_ats = started_ats.astype("datetime64[s]")
    completed_ats = df_check_runs[CheckRun.completed_at.key].values.astype(started_ats.dtype)
    elapseds = completed_ats - started_ats
    elapsed_mask = elapseds == elapseds
    timeline_masks = (timeline[:-1, None] <= started_ats) & (started_ats < timeline[1:, None])
    timeline_elapseds = np.broadcast_to(elapseds[None, :], (len(timeline) - 1, len(elapseds)))

    result = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "All-NaN slice encountered")
        warnings.filterwarnings("ignore", "Mean of empty slice")
        for i, ((repo, _, name), last_execution_time, last_execution_url) in enumerate(zip(
                unique_repo_crnames, last_execution_times, last_execution_urls)):
            masks = {"total": inverse_cr_map == i, "prs": prs_inverse_cr_map == i}
            result.append(CodeCheckRunListItem(
                title=name,
                repository=repo,
                last_execution_time=last_execution_time.item().replace(tzinfo=timezone.utc),
                last_execution_url=last_execution_url,
                size_groups=np.unique(suite_size_map[masks["total"]]).tolist(),
                **{
                    f"{key}_stats": CodeCheckRunListStats(
                        count=mask.sum(),
                        successes=success_mask[mask].sum(),
                        skips=skips_mask[mask].sum(),
                        flaky_count=len(np.intersect1d(commitscol[success_or_skipped_mask & mask],
                                                       commitscol[failure_mask & mask])),
                        mean_execution_time=_val_or_none(np.mean(elapseds[elapsed_mask & (
                            qmask := _tighten_mask_by_quantiles(elapseds, mask, quantiles))])),
                        median_execution_time=_val_or_none(np.median(
                            elapseds[elapsed_mask & mask])),
                        count_timeline=timeline_masks[:, mask].astype(bool).sum(axis=1).tolist(),
                        successes_timeline=timeline_masks[:, success_mask & mask].astype(
                            bool).sum(axis=1).tolist(),
                        mean_execution_time_timeline=np.mean(
                            timeline_elapseds, where=timeline_masks & qmask[None, :], axis=1,
                        ).tolist(),
                        # np.median does not have `where` in 1.20.1
                        # np.nanmedian loses the dtype when axis=1
                        median_execution_time_timeline=np.nanmedian(
                            np.where(timeline_masks & mask[None, :],
                                     timeline_elapseds,
                                     np.timedelta64("NaT")),
                            axis=1).astype(timeline_elapseds.dtype).tolist(),
                    )
                    for key, mask in masks.items()
                },
            ))
    return timeline_dates, result


def _build_timeline(time_from: datetime, time_to: datetime) -> np.ndarray:
    days = (time_to - time_from).days
    if days < 5 * 7:
        timeline = np.array([(time_from + timedelta(days=i)) for i in range(days + 1)],
                            dtype="datetime64[s]")
    elif days < 5 * 30:
        timeline = np.array([(time_from + timedelta(days=i)) for i in range(0, days + 6, 7)],
                            dtype="datetime64[s]")
        timeline[-1] = time_to
    else:
        timeline = list(rrule(MONTHLY, dtstart=time_from, until=time_to, bymonthday=1))
        if timeline[0] > time_from:
            timeline.insert(0, time_from)
        if timeline[-1] < time_to:
            timeline.append(time_to)
        timeline = np.array(timeline, dtype="datetime64[s]")
    return timeline


def _tighten_mask_by_quantiles(elapseds: np.ndarray,
                               mask: np.ndarray,
                               quantiles: Sequence[float],
                               ) -> np.ndarray:
    if quantiles[0] == 0 and quantiles[1] == 1:
        return mask
    samples = elapseds[mask]
    if len(samples) == 0:
        return mask
    mask = mask.copy()
    qmin, qmax = np.nanquantile(samples, quantiles, interpolation="nearest")
    if qmin != qmin:
        mask[:] = False
        return mask
    qmask = (samples < qmin) | (samples > qmax)
    mask[np.nonzero(mask)[0][qmask]] = False
    return mask


def _val_or_none(val):
    if val == val:
        return val.item()
    return None
