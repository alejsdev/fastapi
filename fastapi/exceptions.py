from collections.abc import Mapping, Sequence
from typing import Annotated, Any, TypedDict

from annotated_doc import Doc
from pydantic import BaseModel, create_model
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.exceptions import WebSocketException as StarletteWebSocketException


class EndpointContext(TypedDict, total=False):
    function: str
    path: str
    file: str
    line: int


class HTTPException(StarletteHTTPException):
    """
    An HTTP exception you can raise in your own code to show errors to the client.

    This is for client errors, invalid authentication, invalid data, etc. Not for server
    errors in your code.

    Read more about it in the
    [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/).

    ## Example

    ```python
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    items = {"foo": "The Foo Wrestlers"}


    @app.get("/items/{item_id}")
    async def read_item(item_id: str):
        if item_id not in items:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"item": items[item_id]}
    ```
    """

    # Keep `Any` for compatibility: FastAPI has historically accepted and stored JSON-compatible non-string values.
    # The default Problem Details handler omits those values because RFC 9457 defines `detail` as a string,
    # but custom handlers can still access the original value here.
    detail: Any

    def __init__(
        self,
        status_code: Annotated[
            int,
            Doc(
                """
                HTTP status code to send to the client.

                Read more about it in the
                [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#use-httpexception)
                """
            ),
        ],
        detail: Annotated[
            Any,
            Doc(
                """
                Data describing this error occurrence.

                The default Problem Details handler includes string values in the
                `detail` member and omits non-string values. Use
                `ProblemDetailsException` extensions for structured error contracts.

                Read more about it in the
                [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#use-httpexception)
                """
            ),
        ] = None,
        headers: Annotated[
            Mapping[str, str] | None,
            Doc(
                """
                Any headers to send to the client in the response.

                Read more about it in the
                [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#add-custom-headers)

                """
            ),
        ] = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class ProblemDetailsException(HTTPException):
    """An HTTP exception represented as an RFC 9457 Problem Details object."""

    _standard_members = {"type", "title", "status", "detail", "instance"}
    detail: str | None
    type: str
    title: str | None
    instance: str | None
    extensions: dict[str, Any]

    def __init__(
        self,
        status_code: int,
        *,
        type_: str = "about:blank",
        title: str | None = None,
        detail: str | None = None,
        instance: str | None = None,
        headers: Mapping[str, str] | None = None,
        extensions: Mapping[str, Any] | None = None,
    ) -> None:
        extension_members = dict(extensions or {})
        reserved_members = self._standard_members.intersection(extension_members)
        if reserved_members:
            members = ", ".join(sorted(reserved_members))
            raise ValueError(
                f"Extensions cannot replace reserved Problem Details members: {members}"
            )
        super().__init__(
            status_code=status_code,
            detail=detail if detail is not None else "",
            headers=headers,
        )
        self.detail = detail
        # Starlette stores only status_code, detail, and headers. Keep the remaining
        # RFC 9457 members for FastAPI's Problem Details exception handler.
        self.type = type_
        self.title = title
        self.instance = instance
        self.extensions = extension_members


class WebSocketException(StarletteWebSocketException):
    """
    A WebSocket exception you can raise in your own code to show errors to the client.

    This is for client errors, invalid authentication, invalid data, etc. Not for server
    errors in your code.

    Read more about it in the
    [FastAPI docs for WebSockets](https://fastapi.tiangolo.com/advanced/websockets/).

    ## Example

    ```python
    from typing import Annotated

    from fastapi import (
        Cookie,
        FastAPI,
        WebSocket,
        WebSocketException,
        status,
    )

    app = FastAPI()

    @app.websocket("/items/{item_id}/ws")
    async def websocket_endpoint(
        *,
        websocket: WebSocket,
        session: Annotated[str | None, Cookie()] = None,
        item_id: str,
    ):
        if session is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Session cookie is: {session}")
            await websocket.send_text(f"Message text was: {data}, for item ID: {item_id}")
    ```
    """

    def __init__(
        self,
        code: Annotated[
            int,
            Doc(
                """
                A closing code from the
                [valid codes defined in the specification](https://datatracker.ietf.org/doc/html/rfc6455#section-7.4.1).
                """
            ),
        ],
        reason: Annotated[
            str | None,
            Doc(
                """
                The reason to close the WebSocket connection.

                It is UTF-8-encoded data. The interpretation of the reason is up to the
                application, it is not specified by the WebSocket specification.

                It could contain text that could be human-readable or interpretable
                by the client code, etc.
                """
            ),
        ] = None,
    ) -> None:
        super().__init__(code=code, reason=reason)


RequestErrorModel: type[BaseModel] = create_model("Request")
WebSocketErrorModel: type[BaseModel] = create_model("WebSocket")


class FastAPIError(RuntimeError):
    """
    A generic, FastAPI-specific error.
    """


class DependencyScopeError(FastAPIError):
    """
    A dependency declared that it depends on another dependency with an invalid
    (narrower) scope.
    """


class ValidationException(Exception):
    def __init__(
        self,
        errors: Sequence[Any],
        *,
        endpoint_ctx: EndpointContext | None = None,
    ) -> None:
        self._errors = errors
        self.endpoint_ctx = endpoint_ctx

        ctx = endpoint_ctx or {}
        self.endpoint_function = ctx.get("function")
        self.endpoint_path = ctx.get("path")
        self.endpoint_file = ctx.get("file")
        self.endpoint_line = ctx.get("line")

    def errors(self) -> Sequence[Any]:
        return self._errors

    def _format_endpoint_context(self) -> str:
        if not (self.endpoint_file and self.endpoint_line and self.endpoint_function):
            if self.endpoint_path:
                return f"\n  Endpoint: {self.endpoint_path}"
            return ""

        context = f'\n  File "{self.endpoint_file}", line {self.endpoint_line}, in {self.endpoint_function}'
        if self.endpoint_path:
            context += f"\n    {self.endpoint_path}"
        return context

    def __str__(self) -> str:
        message = f"{len(self._errors)} validation error{'s' if len(self._errors) != 1 else ''}:\n"
        for err in self._errors:
            message += f"  {err}\n"
        message += self._format_endpoint_context()
        return message.rstrip()


class RequestValidationError(ValidationException):
    def __init__(
        self,
        errors: Sequence[Any],
        *,
        body: Any = None,
        endpoint_ctx: EndpointContext | None = None,
    ) -> None:
        super().__init__(errors, endpoint_ctx=endpoint_ctx)
        self.body = body


class WebSocketRequestValidationError(ValidationException):
    def __init__(
        self,
        errors: Sequence[Any],
        *,
        endpoint_ctx: EndpointContext | None = None,
    ) -> None:
        super().__init__(errors, endpoint_ctx=endpoint_ctx)


class ResponseValidationError(ValidationException):
    def __init__(
        self,
        errors: Sequence[Any],
        *,
        body: Any = None,
        endpoint_ctx: EndpointContext | None = None,
    ) -> None:
        super().__init__(errors, endpoint_ctx=endpoint_ctx)
        self.body = body


class PydanticV1NotSupportedError(FastAPIError):
    """
    A pydantic.v1 model is used, which is no longer supported.
    """


class FastAPIDeprecationWarning(UserWarning):
    """
    A custom deprecation warning as DeprecationWarning is ignored
    Ref: https://sethmlarson.dev/deprecations-via-warnings-dont-work-for-python-libraries
    """
