from typing import List, Optional

from athenian.api import serialization
from athenian.api.models.web.base_model_ import Model


class ForSet(Model):
    """This class is auto generated by OpenAPI Generator (https://openapi-generator.tech)."""

    def __init__(
        self,
        repositories: Optional[List[str]] = None,
        developers: Optional[List[str]] = None,
    ):
        """ForSet - a model defined in OpenAPI

        :param repositories: The repositories of this ForSet.
        :param developers: The developers of this ForSet.
        """
        self.openapi_types = {"repositories": List[str], "developers": List[str]}

        self.attribute_map = {
            "repositories": "repositories",
            "developers": "developers",
        }

        self._repositories = repositories
        self._developers = developers or []

    @classmethod
    def from_dict(cls, dikt: dict) -> "ForSet":
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The ForSet of this ForSet.
        """
        return serialization.deserialize_model(dikt, cls)

    @property
    def repositories(self) -> List[str]:
        """Gets the repositories of this ForSet.

        :return: The repositories of this ForSet.
        """
        return self._repositories

    @repositories.setter
    def repositories(self, repositories: List[str]):
        """Sets the repositories of this ForSet.

        :param repositories: The repositories of this ForSet.
        """
        if repositories is None:
            raise ValueError("Invalid value for `repositories`, must not be `None`")

        self._repositories = repositories

    @property
    def developers(self) -> List[str]:
        """Gets the developers of this ForSet.

        :return: The developers of this ForSet.
        """
        return self._developers

    @developers.setter
    def developers(self, developers: List[str]):
        """Sets the developers of this ForSet.

        :param developers: The developers of this ForSet.
        """
        if developers is None:
            raise ValueError("Invalid value for `developers`, must not be `None`")

        self._developers = developers
