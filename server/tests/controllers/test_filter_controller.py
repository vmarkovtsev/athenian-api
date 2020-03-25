from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Optional, Set

from aiohttp import ClientResponse
import dateutil
from prometheus_client import CollectorRegistry
import pytest

from athenian.api import setup_cache_metrics
from athenian.api.controllers.miners.pull_request_list_item import Property
from athenian.api.models.web import CommitsList
from athenian.api.models.web.pull_request_participant import PullRequestParticipant
from athenian.api.models.web.pull_request_pipeline_stage import PullRequestPipelineStage
from athenian.api.models.web.pull_request_property import PullRequestProperty
from tests.conftest import FakeCache


async def test_filter_repositories_no_repos(client, headers):
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
    }
    response = await client.request(
        method="POST", path="/v1/filter/repositories", headers=headers, json=body)
    repos = json.loads((await response.read()).decode("utf-8"))
    assert repos == ["github.com/src-d/go-git"]
    body["date_from"] = body["date_to"]
    response = await client.request(
        method="POST", path="/v1/filter/repositories", headers=headers, json=body)
    assert response.status == 200
    repos = json.loads((await response.read()).decode("utf-8"))
    assert repos == []


async def test_filter_repositories(client, headers):
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        "in": ["github.com/src-d/go-git"],
    }
    response = await client.request(
        method="POST", path="/v1/filter/repositories", headers=headers, json=body)
    repos = json.loads((await response.read()).decode("utf-8"))
    assert repos == ["github.com/src-d/go-git"]
    body["in"] = ["github.com/src-d/gitbase"]
    response = await client.request(
        method="POST", path="/v1/filter/repositories", headers=headers, json=body)
    repos = json.loads((await response.read()).decode("utf-8"))
    assert repos == []


@pytest.mark.parametrize("account, date_to, code",
                         [(3, "2020-01-23", 403), (10, "2020-01-23", 403), (1, "2015-10-13", 200),
                          (1, "2010-01-11", 400), (1, "2020-01-32", 400)])
async def test_filter_repositories_nasty_input(client, headers, account, date_to, code):
    body = {
        "date_from": "2015-10-13",
        "date_to": date_to,
        "account": account,
    }
    response = await client.request(
        method="POST", path="/v1/filter/repositories", headers=headers, json=body)
    assert response.status == code


@pytest.mark.parametrize("in_", [{}, {"in": []}])
async def test_filter_contributors_no_repos(client, headers, in_):
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        **in_,
    }
    response = await client.request(
        method="POST", path="/v1/filter/contributors", headers=headers, json=body)
    contribs = json.loads((await response.read()).decode("utf-8"))
    assert len(contribs) == 178
    assert len(set(contribs)) == len(contribs)
    assert all(c.startswith("github.com/") for c in contribs)
    assert "github.com/mcuadros" in contribs
    body["date_from"] = body["date_to"]
    response = await client.request(
        method="POST", path="/v1/filter/contributors", headers=headers, json=body)
    assert response.status == 200
    contribs = json.loads((await response.read()).decode("utf-8"))
    assert contribs == []


async def test_filter_contributors(client, headers):
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        "in": ["github.com/src-d/go-git"],
    }
    response = await client.request(
        method="POST", path="/v1/filter/contributors", headers=headers, json=body)
    contribs = json.loads((await response.read()).decode("utf-8"))
    assert len(contribs) == 178
    assert len(set(contribs)) == len(contribs)
    assert all(c.startswith("github.com/") for c in contribs)
    assert "github.com/mcuadros" in contribs
    assert "github.com/author_login" not in contribs
    assert "github.com/committer_login" not in contribs
    body["in"] = ["github.com/src-d/gitbase"]
    response = await client.request(
        method="POST", path="/v1/filter/contributors", headers=headers, json=body)
    contribs = json.loads((await response.read()).decode("utf-8"))
    assert contribs == []


@pytest.mark.parametrize("account, date_to, code",
                         [(3, "2020-01-23", 403), (10, "2020-01-23", 403), (1, "2015-10-13", 200),
                          (1, "2010-01-11", 400), (1, "2020-01-32", 400)])
async def test_filter_contributors_nasty_input(client, headers, account, date_to, code):
    body = {
        "date_from": "2015-10-13",
        "date_to": date_to,
        "account": account,
    }
    response = await client.request(
        method="POST", path="/v1/filter/contributors", headers=headers, json=body)
    assert response.status == code


@pytest.fixture(scope="module")
def filter_prs_single_prop_cache():
    fc = FakeCache()
    setup_cache_metrics(fc, CollectorRegistry(auto_describe=True))
    return fc


@pytest.mark.parametrize("stage", PullRequestPipelineStage.ALL)
async def test_filter_prs_single_stage(client, headers, stage, app, filter_prs_single_prop_cache):
    app._cache = filter_prs_single_prop_cache
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        "stages": [stage],
    }
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    if stage in ("wip", "done"):
        props = {stage}
    elif stage in ("merge", "release"):
        props = {stage[:-1] + "ing"}
    else:
        props = {stage + "ing"}
    await validate_prs_response(response, props, stages={stage})


@pytest.mark.parametrize("prop", [k.name.lower() for k in Property])
async def test_filter_prs_single_prop(client, headers, prop, app, filter_prs_single_prop_cache):
    app._cache = filter_prs_single_prop_cache
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        "properties": [prop],
    }
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    await validate_prs_response(response, {prop})


async def test_filter_prs_all_properties(client, headers):
    body = {
        "date_from": "2015-10-13",
        "date_to": "2020-01-23",
        "account": 1,
        "properties": [],
    }
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    await validate_prs_response(response, PullRequestProperty.ALL,
                                stages=PullRequestPipelineStage.ALL)
    del body["properties"]
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    await validate_prs_response(response, PullRequestProperty.ALL,
                                stages=PullRequestPipelineStage.ALL)


async def validate_prs_response(response: ClientResponse, props: Set[str],
                                stages: Optional[Set[str]] = None):
    assert response.status == 200
    obj = json.loads((await response.read()).decode("utf-8"))
    users = obj["include"]["users"]
    assert len(users) > 0
    assert len(obj["data"]) > 0
    statuses = defaultdict(int)
    mentioned_users = set()
    comments = 0
    commits = 0
    review_requested = False
    review_comments = 0
    release_urls = 0
    timestamps = defaultdict(bool)
    response_props = defaultdict(bool)
    for pr in obj["data"]:
        assert pr["repository"].startswith("github.com/"), str(pr)
        assert pr["number"] > 0
        assert pr["title"]
        assert pr["size_added"] + pr["size_removed"] >= 0, str(pr)
        assert pr["files_changed"] >= 0, str(pr)
        assert pr["created"], str(pr)
        for k in ("closed", "updated", "merged", "released"):
            timestamps[k] |= bool(pr.get(k))
        if pr.get("merged"):
            assert pr["closed"], str(pr)
        if pr.get("released"):
            assert pr["merged"], str(pr)
        if stages is not None:
            assert pr["stage"] in stages
        assert props.intersection(set(pr["properties"]))
        comments += pr["comments"]
        commits += pr["commits"]
        review_requested |= pr["review_requested"]
        review_comments += pr["review_comments"]
        release_urls += bool(pr.get("release_url"))
        for prop in pr["properties"]:
            response_props[prop] = True
        participants = pr["participants"]
        assert len(participants) > 0
        authors = 0
        for p in participants:
            assert p["id"].startswith("github.com/")
            mentioned_users.add(p["id"])
            for s in p["status"]:
                statuses[s] += 1
                authors += s == PullRequestParticipant.STATUS_AUTHOR
                assert s in PullRequestParticipant.STATUSES
        if pr["number"] != 749:
            # the author of 749 is deleted on GitHub
            assert authors == 1
    assert not (set(users) - mentioned_users)
    assert commits > 0
    assert timestamps["updated"]
    if PullRequestProperty.WIP in props:
        assert statuses[PullRequestParticipant.STATUS_COMMIT_COMMITTER] > 0
        assert statuses[PullRequestParticipant.STATUS_COMMIT_AUTHOR] > 0
        assert response_props.get("wip")
        assert response_props.get("created")
        assert response_props.get("commit_happened")
    if PullRequestProperty.REVIEWING in props:
        assert comments > 0
        assert review_comments > 0
        assert statuses[PullRequestParticipant.STATUS_REVIEWER] > 0
        assert response_props.get("reviewing")
        assert response_props.get("review_happened")
        assert response_props.get("commit_happened")
    if PullRequestProperty.MERGING in props:
        assert review_requested
        assert comments > 0
        assert review_comments >= 0
        assert statuses[PullRequestParticipant.STATUS_REVIEWER] > 0
        assert response_props.get("merging")
        assert response_props.get("commit_happened")
        assert response_props.get("review_happened")
        assert response_props.get("approve_happened")
    if PullRequestProperty.RELEASING in props:
        assert review_requested
        assert comments > 0
        assert review_comments >= 0
        assert statuses[PullRequestParticipant.STATUS_REVIEWER] > 0
        assert statuses[PullRequestParticipant.STATUS_MERGER] > 0
        assert response_props.get("releasing")
        assert response_props.get("merge_happened")
        assert timestamps["merged"]
    if PullRequestProperty.DONE in props:
        assert review_requested
        assert comments > 0
        assert review_comments > 0
        assert statuses[PullRequestParticipant.STATUS_REVIEWER] > 0
        assert statuses[PullRequestParticipant.STATUS_MERGER] > 0
        assert statuses[PullRequestParticipant.STATUS_RELEASER] > 0
        assert response_props.get("done")
        assert response_props.get("release_happened")
        assert timestamps["released"]
        assert timestamps["closed"]


@pytest.mark.parametrize("account, date_to, code",
                         [(3, "2020-01-23", 403), (10, "2020-01-23", 403), (1, "2015-10-13", 200),
                          (1, "2010-01-11", 400), (1, "2020-01-32", 400)])
async def test_filter_prs_nasty_input(client, headers, account, date_to, code):
    body = {
        "date_from": "2015-10-13",
        "date_to": date_to,
        "account": account,
        "properties": [],
    }
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    assert response.status == code


async def test_filter_prs_david_bug(client, headers):
    body = {
        "account": 1,
        "date_from": "2019-02-22",
        "date_to": "2020-02-22",
        "in": ["github.com/src-d/go-git"],
        "properties": ["wip", "reviewing", "merging", "releasing"],
        "with": {
            "author": ["github.com/Junnplus"],
            "reviewer": ["github.com/Junnplus"],
            "commit_author": ["github.com/Junnplus"],
            "commit_committer": ["github.com/Junnplus"],
            "commenter": ["github.com/Junnplus"],
            "merger": ["github.com/Junnplus"],
        },
    }
    response = await client.request(
        method="POST", path="/v1/filter/pull_requests", headers=headers, json=body)
    assert response.status == 200


async def test_filter_commits_bypassing_prs_mcuadros(client, headers):
    body = {
        "account": 1,
        "date_from": "2019-01-12",
        "date_to": "2020-02-22",
        "in": ["{1}"],
        "property": "bypassing_prs",
        "with_author": ["github.com/mcuadros"],
        "with_committer": ["github.com/mcuadros"],
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(json.loads((await response.read()).decode("utf-8")))
    assert commits.to_dict() == {
        "data": [{"author": {"email": "mcuadros@gmail.com",
                             "login": "github.com/mcuadros",
                             "name": "Máximo Cuadros",
                             "timestamp": datetime(2019, 4, 24, 13, 20, 51, tzinfo=timezone.utc),
                             "timezone": 2.0},
                  "committer": {"email": "mcuadros@gmail.com",
                                "login": "github.com/mcuadros",
                                "name": "Máximo Cuadros",
                                "timestamp": datetime(2019, 4, 24, 13, 20, 51,
                                                      tzinfo=timezone.utc),
                                "timezone": 2.0},
                  "files_changed": 1,
                  "hash": "5c6d199dc675465f5e103ea36c0bfcb9d3ebc565",
                  "message": "plumbing: commit.Stats, fix panic on empty chucks\n\n"
                             "Signed-off-by: Máximo Cuadros <mcuadros@gmail.com>",
                  "repository": "src-d/go-git",
                  "size_added": 4,
                  "size_removed": 0}],
        "include": {"users": {
            "github.com/mcuadros": {
                "avatar": "https://avatars0.githubusercontent.com/u/1573114?s=600&v=4"}}}}


async def test_filter_commits_no_pr_merges_mcuadros(client, headers):
    body = {
        "account": 1,
        "date_from": "2019-01-12",
        "date_to": "2020-02-22",
        "in": ["{1}"],
        "property": "no_pr_merges",
        "with_author": ["github.com/mcuadros"],
        "with_committer": ["github.com/mcuadros"],
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(json.loads((await response.read()).decode("utf-8")))
    assert len(commits.data) == 6
    assert len(commits.include.users) == 1
    for c in commits.data:
        assert c.author.login == "github.com/mcuadros"
        assert c.committer.login == "github.com/mcuadros"


async def test_filter_commits_bypassing_prs_merges(client, headers):
    body = {
        "account": 1,
        "date_from": "2019-01-12",
        "date_to": "2020-02-22",
        "in": ["{1}"],
        "property": "bypassing_prs",
        "with_author": [],
        "with_committer": [],
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(json.loads((await response.read()).decode("utf-8")))
    assert len(commits.data) == 25
    for c in commits.data:
        assert c.committer.email != "noreply@github.com"


async def test_filter_commits_bypassing_prs_empty(client, headers):
    body = {
        "account": 1,
        "date_from": "2020-01-12",
        "date_to": "2020-02-22",
        "in": ["{1}"],
        "property": "bypassing_prs",
        "with_author": ["github.com/mcuadros"],
        "with_committer": ["github.com/mcuadros"],
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(json.loads((await response.read()).decode("utf-8")))
    assert len(commits.data) == 0
    assert len(commits.include.users) == 0


async def test_filter_commits_bypassing_prs_no_with(client, headers):
    body = {
        "account": 1,
        "date_from": "2020-01-12",
        "date_to": "2020-02-21",
        "in": ["{1}"],
        "property": "bypassing_prs",
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(
        json.loads((await response.read()).decode("utf-8")))  # type: CommitsList
    assert len(commits.data) == 0
    assert len(commits.include.users) == 0
    body["date_to"] = "2020-02-22"
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == 200
    commits = CommitsList.from_dict(json.loads((await response.read()).decode("utf-8")))
    assert len(commits.data) == 1
    assert commits.data[0].committer.timestamp == datetime(2020, 2, 22, 18, 58, 50,
                                                           tzinfo=dateutil.tz.tzutc())


@pytest.mark.parametrize("account, date_to, code",
                         [(3, "2020-02-22", 403), (10, "2020-02-22", 403), (1, "2020-01-12", 200),
                          (1, "2010-01-11", 400), (1, "2020-02-32", 400)])
async def test_filter_commits_bypassing_prs_nasty_input(client, headers, account, date_to, code):
    body = {
        "account": account,
        "date_from": "2020-01-12",
        "date_to": date_to,
        "in": ["{1}"],
        "property": "bypassing_prs",
    }
    response = await client.request(
        method="POST", path="/v1/filter/commits", headers=headers, json=body)
    assert response.status == code
