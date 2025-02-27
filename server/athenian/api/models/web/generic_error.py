from http import HTTPStatus
from typing import Optional

from athenian.api.models.web.base_model_ import Model


class GenericError(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    attribute_types = {
        "type": str,
        "title": str,
        "status": Optional[int],
        "detail": Optional[str],
        "instance": Optional[str],
    }

    attribute_map = {
        "type": "type",
        "title": "title",
        "status": "status",
        "detail": "detail",
        "instance": "instance",
    }

    def __init__(
        self,
        type: str,
        title: Optional[str] = None,
        status: Optional[int] = None,
        detail: Optional[str] = None,
        instance: Optional[str] = None,
    ):
        """GenericError - a model defined in OpenAPI

        :param type: The type of this GenericError.
        :param title: The title of this GenericError.
        :param status: The status of this GenericError.
        :param detail: The detail of this GenericError.
        :param instance: The instance of this GenericError.
        """
        self._type = type
        self._title = title
        self._status = status
        self._detail = detail
        self._instance = instance

    @property
    def type(self) -> str:
        """Gets the type of this GenericError.

        URI reference that identifies the problem type (RFC 7807).

        :return: The type of this GenericError.
        """
        return self._type

    @type.setter
    def type(self, type: str):
        """Sets the type of this GenericError.

        URI reference that identifies the problem type (RFC 7807).

        :param type: The type of this GenericError.
        """
        if type is None:
            raise ValueError("Invalid value for `type`, must not be `None`")

        self._type = type

    @property
    def title(self) -> str:
        """Gets the title of this GenericError.

        Short, human-readable summary of the problem type.

        :return: The title of this GenericError.
        """
        return self._title

    @title.setter
    def title(self, title: str):
        """Sets the title of this GenericError.

        Short, human-readable summary of the problem type.

        :param title: The title of this GenericError.
        """
        self._title = title

    @property
    def status(self) -> Optional[int]:
        """Gets the status of this GenericError.

        Duplicated HTTP status code.

        :return: The status of this GenericError.
        """
        return self._status

    @status.setter
    def status(self, status: Optional[int]):
        """Sets the status of this GenericError.

        Duplicated HTTP status code.

        :param status: The status of this GenericError.
        """
        self._status = status

    @property
    def detail(self) -> Optional[str]:
        """Gets the detail of this GenericError.

        Human-readable explanation specific to this occurrence of the problem.

        :return: The detail of this GenericError.
        """
        return self._detail

    @detail.setter
    def detail(self, detail: Optional[str]):
        """Sets the detail of this GenericError.

        Human-readable explanation specific to this occurrence of the problem.

        :param detail: The detail of this GenericError.
        """
        self._detail = detail

    @property
    def instance(self) -> Optional[str]:
        """Gets the instance of this GenericError.

        URI reference that identifies the specific occurrence of the problem.

        :return: The instance of this GenericError.
        """
        return self._instance

    @instance.setter
    def instance(self, instance: Optional[str]):
        """Sets the instance of this GenericError.

        URI reference that identifies the specific occurrence of the problem.

        :param instance: The instance of this GenericError.
        """
        self._instance = instance


class BadRequestError(GenericError):
    """HTTP 400."""

    def __init__(self, detail: Optional[str] = None):
        """Initialize a new instance of BadRequestError.

        :param detail: The details about this error.
        """
        super().__init__(
            type="/errors/BadRequest",
            title=HTTPStatus.BAD_REQUEST.phrase,
            status=HTTPStatus.BAD_REQUEST,
            detail=detail,
        )


class NotFoundError(GenericError):
    """HTTP 404."""

    def __init__(self, detail: Optional[str] = None, type_: str = "/errors/NotFoundError"):
        """Initialize a new instance of NotFoundError.

        :param detail: The details about this error.
        """
        super().__init__(
            type=type_,
            title=HTTPStatus.NOT_FOUND.phrase,
            status=HTTPStatus.NOT_FOUND,
            detail=detail,
        )


class ForbiddenError(GenericError):
    """HTTP 403."""

    def __init__(self, detail: Optional[str] = None):
        """Initialize a new instance of ForbiddenError.

        :param detail: The details about this error.
        """
        super().__init__(
            type="/errors/ForbiddenError",
            title=HTTPStatus.FORBIDDEN.phrase,
            status=HTTPStatus.FORBIDDEN,
            detail=detail,
        )


class UnauthorizedError(GenericError):
    """HTTP 401."""

    def __init__(self, detail: Optional[str] = None):
        """Initialize a new instance of UnauthorizedError.

        :param detail: The details about this error.
        """
        super().__init__(
            type="/errors/Unauthorized",
            title=HTTPStatus.UNAUTHORIZED.phrase,
            status=HTTPStatus.UNAUTHORIZED,
            detail=detail,
        )


class DatabaseConflict(GenericError):
    """HTTP 409."""

    def __init__(self, detail: Optional[str] = None):
        """Initialize a new instance of DatabaseConflict.

        :param detail: The details about this error.
        """
        super().__init__(
            type="/errors/DatabaseConflict",
            title=HTTPStatus.CONFLICT.phrase,
            status=HTTPStatus.CONFLICT,
            detail=detail,
        )


class TooManyRequestsError(GenericError):
    """HTTP 429."""

    def __init__(self, detail: Optional[str] = None, type="/errors/TooManyRequestsError"):
        """Initialize a new instance of TooManyRequestsError.

        :param detail: The details about this error.
        :param type: The type identifier of this error.
        """
        super().__init__(
            type=type,
            title=HTTPStatus.TOO_MANY_REQUESTS.phrase,
            status=HTTPStatus.TOO_MANY_REQUESTS,
            detail=detail,
        )


class ServerNotImplementedError(GenericError):
    """HTTP 501."""

    def __init__(self, detail="This API endpoint is not implemented yet."):
        """Initialize a new instance of ServerNotImplementedError.

        :param detail: The details about this error.
        """
        super().__init__(
            type="/errors/NotImplemented",
            title=HTTPStatus.NOT_IMPLEMENTED.phrase,
            status=HTTPStatus.NOT_IMPLEMENTED,
            detail=detail,
        )


class ServiceUnavailableError(GenericError):
    """HTTP 503."""

    def __init__(self, type: str, detail: Optional[str], instance: Optional[str] = None):
        """Initialize a new instance of ServiceUnavailableError.

        :param detail: The details about this error.
        :param type: The type identifier of this error.
        :param instance: Sentry event ID of this error.
        """
        super().__init__(
            type=type,
            title=HTTPStatus.SERVICE_UNAVAILABLE.phrase,
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=detail,
            instance=instance,
        )
