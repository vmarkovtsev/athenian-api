from __future__ import annotations

from typing import List, Optional, Type, TypeVar

from athenian.api.models.web.base_model_ import Model
from athenian.api.models.web.jira_filter import JIRAFilter

ForSetLike = TypeVar("ForSetLike", bound=Model)


class RepositoryGroupsMixin:
    """Mixin to add support for `repositories` and `repogroups`."""

    @property
    def repositories(self) -> List[str]:
        """Gets the repositories of this ForSetPullRequests.

        :return: The repositories of this ForSetPullRequests.
        """
        return self._repositories

    @repositories.setter
    def repositories(self, repositories: List[str]):
        """Sets the repositories of this ForSetPullRequests.

        :param repositories: The repositories of this ForSetPullRequests.
        """
        if repositories is None:
            raise ValueError("Invalid value for `repositories`, must not be `None`")
        if len(repositories) == 0:
            raise ValueError("Invalid value for `repositories`, must not be an empty list")
        if self._repogroups is not None:
            for i, group in enumerate(self._repogroups):
                for j, v in enumerate(group):
                    if v >= len(repositories):
                        raise ValueError(
                            "`repogroups[%d][%d]` = %s must be less than the number of "
                            "repositories (%d)" % (i, j, v, len(repositories)),
                        )

        self._repositories = repositories

    @property
    def repogroups(self) -> Optional[List[List[int]]]:
        """Gets the repogroups of this ForSetPullRequests.

        :return: The repogroups of this ForSetPullRequests.
        """
        return self._repogroups

    @repogroups.setter
    def repogroups(self, repogroups: Optional[List[List[int]]]):
        """Sets the repogroups of this ForSetPullRequests.

        :param repogroups: The repogroups of this ForSetPullRequests.
        """
        if repogroups is not None:
            if len(repogroups) == 0:
                raise ValueError("`repogroups` must contain at least one list")
            for i, group in enumerate(repogroups):
                if len(group) == 0:
                    raise ValueError("`repogroups[%d]` must contain at least one element" % i)
                for j, v in enumerate(group):
                    if v < 0:
                        raise ValueError(
                            "`repogroups[%d][%d]` = %s must not be negative" % (i, j, v),
                        )
                    if self._repositories is not None and v >= len(self._repositories):
                        raise ValueError(
                            "`repogroups[%d][%d]` = %s must be less than the number of "
                            "repositories (%d)" % (i, j, v, len(self._repositories)),
                        )
                if len(set(group)) < len(group):
                    raise ValueError("`repogroups[%d]` has duplicate items" % i)

        self._repogroups = repogroups

    def select_repogroup(self: ForSetLike, index: int) -> ForSetLike:
        """Change `repositories` to point at the specified group and clear `repogroups`."""
        fs = self.copy()
        if not self.repogroups:
            if index > 0:
                raise IndexError("%d is out of range (no repogroups)" % index)
            return fs
        if index >= len(self.repogroups):
            raise IndexError("%d is out of range (max is %d)" % (index, len(self.repogroups)))
        fs.repogroups = None
        fs.repositories = [self.repositories[i] for i in self.repogroups[index]]
        return fs


def make_common_pull_request_filters(prefix_labels: str) -> Type[Model]:
    """Generate CommonPullRequestFilters class with the specified label properties name prefix."""

    class CommonPullRequestFilters(Model, sealed=False):
        """A few filters that are specific to filtering PR-related entities."""

        attribute_types = {
            prefix_labels + "labels_include": Optional[List[str]],
            prefix_labels + "labels_exclude": Optional[List[str]],
            "jira": Optional[JIRAFilter],
        }

        attribute_map = {
            prefix_labels + "labels_include": prefix_labels + "labels_include",
            prefix_labels + "labels_exclude": prefix_labels + "labels_exclude",
            "jira": "jira",
        }

        def __init__(self, **kwargs):
            """Will be overwritten later."""
            setattr(self, li_name := f"_{prefix_labels}labels_include", kwargs.get(li_name[1:]))
            setattr(self, le_name := f"_{prefix_labels}labels_exclude", kwargs.get(le_name[1:]))
            self._jira = kwargs.get("jira")

        def _get_labels_include(self) -> Optional[List[str]]:
            """Gets the labels_include of this CommonPullRequestFilters.

            :return: The labels_include of this CommonPullRequestFilters.
            """
            return getattr(self, f"_{prefix_labels}labels_include")

        def _set_labels_include(self, labels_include: Optional[List[str]]) -> None:
            """Sets the labels_include of this CommonPullRequestFilters.

            :param labels_include: The labels_include of this CommonPullRequestFilters.
            """
            setattr(self, f"_{prefix_labels}labels_include", labels_include)

        def _get_labels_exclude(self) -> Optional[List[str]]:
            """Gets the labels_exclude of this CommonPullRequestFilters.

            :return: The labels_exclude of this CommonPullRequestFilters.
            """
            return getattr(self, f"_{prefix_labels}labels_exclude")

        def _set_labels_exclude(self, labels_exclude: Optional[List[str]]) -> None:
            """Sets the labels_exclude of this CommonPullRequestFilters.

            :param labels_exclude: The labels_exclude of this CommonPullRequestFilters.
            """
            setattr(self, f"_{prefix_labels}labels_exclude", labels_exclude)

        @property
        def jira(self) -> Optional[JIRAFilter]:
            """Gets the jira of this CommonPullRequestFilters.

            :return: The jira of this CommonPullRequestFilters.
            """
            return self._jira

        @jira.setter
        def jira(self, jira: Optional[JIRAFilter]) -> None:
            """Sets the jira of this CommonPullRequestFilters.

            :param jira: The jira of this CommonPullRequestFilters.
            """
            self._jira = jira

    # we cannot do this at once because it crashes the ast module
    CommonPullRequestFilters.__init__.__doc__ = f"""
    Initialize a new instance of CommonPullRequestFilters.

    :param {prefix_labels}labels_include: The labels_include of this CommonPullRequestFilters.
    :param {prefix_labels}labels_exclude: The labels_exclude of this CommonPullRequestFilters.
    :param jira: The jira of this CommonPullRequestFilters.
    """

    setattr(
        CommonPullRequestFilters,
        prefix_labels + "labels_include",
        property(
            CommonPullRequestFilters._get_labels_include,
            CommonPullRequestFilters._set_labels_include,
        ),
    )
    setattr(
        CommonPullRequestFilters,
        prefix_labels + "labels_exclude",
        property(
            CommonPullRequestFilters._get_labels_exclude,
            CommonPullRequestFilters._set_labels_exclude,
        ),
    )

    return CommonPullRequestFilters


CommonPullRequestFilters = make_common_pull_request_filters("")


class ForSetLines(Model, RepositoryGroupsMixin, sealed=False):
    """Support for splitting metrics by the number of changed lines."""

    attribute_types = {
        "repositories": List[str],
        "repogroups": Optional[List[List[int]]],
        "lines": Optional[List[int]],
    }

    attribute_map = {
        "repositories": "repositories",
        "repogroups": "repogroups",
        "lines": "lines",
    }

    def __init__(
        self,
        repositories: Optional[List[str]] = None,
        repogroups: Optional[List[List[int]]] = None,
        lines: Optional[List[int]] = None,
    ):
        """ForSetLines - support for splitting metrics by the number of changed lines.

        :param repositories: The repositories of this ForSetPullRequests.
        :param repogroups: The repogroups of this ForSetPullRequests.
        :param lines: The lines of this ForSetPullRequests.
        """
        self._repositories = repositories
        self._repogroups = repogroups
        self._lines = lines

    @property
    def lines(self) -> Optional[List[int]]:
        """Gets the lines of this ForSetPullRequests.

        :return: The lines of this ForSetPullRequests.
        """
        return self._lines

    @lines.setter
    def lines(self, lines: Optional[List[int]]):
        """Sets the lines of this ForSetPullRequests.

        :param lines: The lines of this ForSetPullRequests.
        """
        if lines is not None:
            if len(lines) < 2:
                raise ValueError("`lines` must contain at least 2 elements")
            if lines[0] < 0:
                raise ValueError("all elements of `lines` must be non-negative")
            for i, val in enumerate(lines[:-1]):
                if val >= lines[i + 1]:
                    raise ValueError("`lines` must monotonically increase")
        self._lines = lines

    def select_lines(self, index: int) -> ForSetLines:
        """Change `lines` to point at the specified line range."""
        fs = self.copy()
        if self.lines is None:
            if index > 0:
                raise IndexError("%d is out of range (no lines)" % index)
            return fs
        if index >= len(self.lines) - 1:
            raise IndexError("%d is out of range (max is %d)" % (index, len(self.lines) - 1))
        fs.lines = [fs.lines[index], fs.lines[index + 1]]
        return fs
