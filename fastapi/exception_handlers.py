import http.client
from collections.abc import Mapping
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import (
    ProblemDetailsException,
    RequestValidationError,
    WebSocketRequestValidationError,
)
from fastapi.problem_details import (
    PROBLEM_DETAILS_MEDIA_TYPE,
    REQUEST_VALIDATION_PROBLEM_TYPE,
    ProblemDetails,
)
from fastapi.utils import is_body_allowed_for_status_code
from fastapi.websockets import WebSocket
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import WS_1008_POLICY_VIOLATION

# RFC 9457 recommends that the title for about:blank match the HTTP status phrase.
# Python still exposes the old names for these renamed statuses.
_RFC_9110_STATUS_TITLES = {
    413: "Content Too Large",
    414: "URI Too Long",
    416: "Range Not Satisfiable",
    422: "Unprocessable Content",
}


def _title_for_status(status_code: int) -> str | None:
    return _RFC_9110_STATUS_TITLES.get(status_code) or http.client.responses.get(
        status_code
    )


def _problem_headers(headers: Mapping[str, str] | None) -> dict[str, str] | None:
    if headers is None:
        return None
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"content-length", "content-type"}
    }


def _generic_detail(detail: Any, *, status_code: int, title: str | None) -> str | None:
    legacy_title = http.client.responses.get(status_code)

    if detail is None or detail == title or detail == legacy_title:
        return None

    if isinstance(detail, str):
        return detail

    return None


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    headers = getattr(exc, "headers", None)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)

    default_title = _title_for_status(exc.status_code)
    if isinstance(exc, ProblemDetailsException):
        problem_data: dict[str, Any] = {
            "type": exc.type,
            "title": (
                default_title
                if exc.title is None and exc.type == "about:blank"
                else exc.title
            ),
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": exc.instance,
        }
        problem_data.update(exc.extensions)
        problem = ProblemDetails.model_validate(problem_data)
    else:
        problem = ProblemDetails(
            title=default_title,
            status=exc.status_code,
            detail=_generic_detail(
                exc.detail,
                status_code=exc.status_code,
                title=default_title,
            ),
        )

    return JSONResponse(
        content=jsonable_encoder(problem),
        status_code=exc.status_code,
        headers=_problem_headers(headers),
        media_type=PROBLEM_DETAILS_MEDIA_TYPE,
    )


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "type": error["type"],
            "loc": jsonable_encoder(error["loc"]),
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]
    problem = ProblemDetails.model_validate(
        {
            "type": REQUEST_VALIDATION_PROBLEM_TYPE,
            "title": "Request validation failed",
            "status": 422,
            "detail": "One or more request values are invalid.",
            "errors": errors,
        }
    )
    return JSONResponse(
        status_code=422,
        media_type=PROBLEM_DETAILS_MEDIA_TYPE,
        content=jsonable_encoder(problem),
    )


async def internal_server_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    problem = ProblemDetails(title="Internal Server Error", status=500)
    return JSONResponse(
        status_code=500,
        media_type=PROBLEM_DETAILS_MEDIA_TYPE,
        content=jsonable_encoder(problem),
    )


async def websocket_request_validation_exception_handler(
    websocket: WebSocket, exc: WebSocketRequestValidationError
) -> None:
    await websocket.close(
        code=WS_1008_POLICY_VIOLATION, reason=jsonable_encoder(exc.errors())
    )
