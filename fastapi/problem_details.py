from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

PROBLEM_DETAILS_MEDIA_TYPE = "application/problem+json"
REQUEST_VALIDATION_PROBLEM_TYPE = (
    "https://fastapi.tiangolo.com/problems/request-validation"
)


class ProblemDetails(BaseModel):
    """The standard members of an RFC 9457 Problem Details object."""
    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str | None = None
    status: int | None = Field(default=None, ge=100, le=599)
    detail: str | None = None
    instance: str | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        return {
            key: value
            for key, value in data.items()
            if key not in {"title", "status", "detail", "instance"} or value is not None
        }
