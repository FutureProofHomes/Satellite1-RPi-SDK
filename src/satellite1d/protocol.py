"""Versioned local protocol shared by the daemon and its CLI client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_MESSAGE_SIZE = 64 * 1024


class ProtocolError(ValueError):
    """A request cannot be processed by the local daemon protocol."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Request:
    request_id: int | str
    method: str
    params: dict[str, Any]


def parse_request(payload: Any) -> Request:
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_request", "request must be an object")
    request_id = payload.get("id")
    if not isinstance(request_id, (int, str)) or isinstance(request_id, bool):
        raise ProtocolError(
            "invalid_request", "request id must be an integer or string"
        )
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise ProtocolError(
            "invalid_request", "request method must be a non-empty string"
        )
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("invalid_request", "request params must be an object")
    return Request(request_id=request_id, method=method, params=params)


def success(request_id: int | str, result: dict[str, Any]) -> dict[str, Any]:
    return {"id": request_id, "result": result}


def failure(request_id: int | str | None, code: str, message: str) -> dict[str, Any]:
    return {"id": request_id, "error": {"code": code, "message": message}}
