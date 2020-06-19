from typing import List, Optional

from athenian.api.models.web.base_model_ import Model


class RepositorySetCreateRequest(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    openapi_types = {
        "account": int,
        "items": List[str],
        "name": str,
    }

    attribute_map = {
        "account": "account",
        "items": "items",
        "name": "name",
    }

    def __init__(self,
                 account: Optional[int] = None,
                 items: Optional[List[str]] = None,
                 name: Optional[str] = None):
        """RepositorySetCreateRequest - a model defined in OpenAPI

        :param account: The account of this RepositorySetCreateRequest.
        :param items: The items of this RepositorySetCreateRequest.
        """
        self._account = account
        self._items = items
        self._name = name

    @property
    def account(self) -> int:
        """Gets the account of this RepositorySetCreateRequest.

        Account identifier. That account will own the created repository set.
        The user must be an admin of the account.

        :return: The account of this RepositorySetCreateRequest.
        """
        return self._account

    @account.setter
    def account(self, account: int):
        """Sets the account of this RepositorySetCreateRequest.

        Account identifier. That account will own the created repository set.
        The user must be an admin of the account.

        :param account: The account of this RepositorySetCreateRequest.
        """
        if account is None:
            raise ValueError("Invalid value for `account`, must not be `None`")

        self._account = account

    @property
    def name(self) -> int:
        """Gets the name of this RepositorySetCreateRequest.

        Unique editable identifier of the repository set.

        :return: The name of this RepositorySetCreateRequest.
        """
        return self._name

    @name.setter
    def name(self, name: int):
        """Sets the name of this RepositorySetCreateRequest.

        Unique editable identifier of the repository set.

        :param name: The name of this RepositorySetCreateRequest.
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")

        self._name = name

    @property
    def items(self) -> List[str]:
        """Gets the items of this RepositorySetCreateRequest.

        :return: The items of this RepositorySetCreateRequest.
        """
        return self._items

    @items.setter
    def items(self, items: List[str]):
        """Sets the items of this RepositorySetCreateRequest.

        :param items: The items of this RepositorySetCreateRequest.
        """
        if items is None:
            raise ValueError("Invalid value for `items`, must not be `None`")

        self._items = items
