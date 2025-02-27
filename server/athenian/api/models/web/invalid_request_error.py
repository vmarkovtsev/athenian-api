from http import HTTPStatus
from typing import Optional

from athenian.api.models.web.generic_error import GenericError


class InvalidRequestError(GenericError):
    """This class is auto generated by OpenAPI Generator (https://openapi-generator.tech)."""

    attribute_types = GenericError.attribute_types.copy()
    attribute_types["pointer"] = str
    attribute_map = GenericError.attribute_map.copy()
    attribute_map["pointer"] = "pointer"

    def __init__(
        self,
        pointer: str,
        detail: Optional[str] = None,
        instance: Optional[str] = None,
    ):
        """InvalidRequestError - a model defined in OpenAPI

        :param title: The title of this InvalidRequestError.
        :param status: The status of this InvalidRequestError.
        :param detail: The detail of this InvalidRequestError.
        :param instance: The instance of this InvalidRequestError.
        :param pointer: The pointer of this InvalidRequestError.
        """
        super().__init__(
            type="/errors/InvalidRequestError",
            title=HTTPStatus.BAD_REQUEST.phrase,
            status=HTTPStatus.BAD_REQUEST,
            detail=detail,
            instance=instance,
        )
        self._pointer = pointer

    @property
    def pointer(self) -> str:
        """Gets the pointer of this InvalidRequestError.

        Path to the offending request item.

        :return: The pointer of this InvalidRequestError.
        """
        return self._pointer

    @pointer.setter
    def pointer(self, pointer: str):
        """Sets the pointer of this InvalidRequestError.

        Path to the offending request item.

        :param pointer: The pointer of this InvalidRequestError.
        """
        if pointer is None:
            raise ValueError("Invalid value for `pointer`, must not be `None`")

        self._pointer = pointer
