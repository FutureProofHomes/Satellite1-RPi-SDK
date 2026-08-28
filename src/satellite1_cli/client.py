"""Async client for the local Satellite1 daemon."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

DEFAULT_SOCKET_PATH = Path("/run/satellite1/satellite1d.sock")


class DaemonClientError(RuntimeError):
    pass


class DaemonClient:
    def __init__(self, socket_path: Path, timeout: float = 10.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_unix_connection(self.socket_path)
                try:
                    writer.write(
                        json.dumps(
                            {"id": 1, "method": method, "params": params or {}}
                        ).encode()
                        + b"\n"
                    )
                    await writer.drain()
                    line = await reader.readline()
                finally:
                    writer.close()
                    await writer.wait_closed()
        except (OSError, TimeoutError) as exc:
            raise DaemonClientError(
                f"cannot connect to satellite1d at {self.socket_path}: {exc}"
            ) from exc

        if not line:
            raise DaemonClientError(
                "satellite1d closed the connection without a response"
            )
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DaemonClientError("satellite1d returned invalid JSON") from exc
        error = response.get("error")
        if error:
            raise DaemonClientError(error.get("message", "satellite1d request failed"))
        result = response.get("result")
        if not isinstance(result, dict):
            raise DaemonClientError("satellite1d returned an invalid response")
        return result
