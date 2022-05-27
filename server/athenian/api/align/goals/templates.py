from athenian.api.models.web import JIRAMetricID, PullRequestMetricID, ReleaseMetricID

TEMPLATES_COLLECTION = {
    1: {
        "metric": PullRequestMetricID.PR_REVIEW_TIME,
    },
    2: {
        "metric": PullRequestMetricID.PR_REVIEW_COMMENTS_PER,
    },
    3: {
        "metric": PullRequestMetricID.PR_MEDIAN_SIZE,
    },
    4: {
        "metric": PullRequestMetricID.PR_LEAD_TIME,
    },
    5: {
        "metric": ReleaseMetricID.RELEASE_COUNT,
    },
    6: {
        "metric": JIRAMetricID.JIRA_RESOLVED,
    },
    7: {
        "metric": PullRequestMetricID.PR_ALL_MAPPED_TO_JIRA,
    },
}
