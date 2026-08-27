"""Async Unix-socket server for local Satellite1 clients."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

from satellite1._protocol import (
    MAX_MESSAGE_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
    failure,
    parse_request,
    success,
)

from . import SERVICE_NAME
from .hardware import HardwareController, HardwareError

DEFAULT_SOCKET_PATH = Path("/run/satellite1/satellite1d.sock")
log = logging.getLogger(__name__)


class Satellite1dServer:
    """Serve local daemon RPC requests."""

    def __init__(
        self,
        hardware: HardwareController | None = None,
        socket_path: Path = DEFAULT_SOCKET_PATH,
    ) -> None:
        self.hardware = hardware
        self.socket_path = socket_path
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.socket_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        self._remove_stale_socket()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
            limit=MAX_MESSAGE_SIZE,
        )
        os.chmod(self.socket_path, 0o660)

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("server is not started")
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._remove_stale_socket()

    def _remove_stale_socket(self) -> None:
        try:
            mode = self.socket_path.lstat().st_mode
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(
                f"refusing to replace non-socket path: {self.socket_path}"
            )
        self.socket_path.unlink()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while line := await reader.readline():
                response = await self._handle_message(line)
                writer.write(
                    json.dumps(response, separators=(",", ":")).encode() + b"\n"
                )
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _handle_message(self, line: bytes) -> dict[str, Any]:
        if len(line) > MAX_MESSAGE_SIZE:
            return failure(None, "message_too_large", "request exceeds size limit")
        try:
            payload = json.loads(line)
            request = parse_request(payload)
            return await self._dispatch(
                request.method, request.params, request.request_id
            )
        except json.JSONDecodeError:
            return failure(None, "invalid_json", "request must contain valid JSON")
        except ProtocolError as exc:
            return failure(None, exc.code, str(exc))

    async def _dispatch(
        self,
        method: str,
        params: dict[str, Any],
        request_id: int | str,
    ) -> dict[str, Any]:
        if method == "hello":
            return success(
                request_id,
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "service": SERVICE_NAME,
                    "capabilities": self._capabilities(),
                },
            )
        if method == "system.health":
            if self.hardware is None:
                return success(request_id, {"status": "healthy"})
            return success(request_id, await self.hardware.health())
        if self.hardware is None:
            return failure(
                request_id, "method_not_found", f"unsupported method: {method}"
            )
        try:
            return success(request_id, await self.hardware.dispatch(method, params))
        except KeyError:
            return failure(
                request_id, "method_not_found", f"unsupported method: {method}"
            )
        except ValueError as exc:
            return failure(request_id, "invalid_params", str(exc))
        except HardwareError as exc:
            return failure(request_id, "hardware_failure", str(exc))
        except Exception:
            log.exception("hardware operation failed: %s", method)
            return failure(request_id, "hardware_failure", "hardware operation failed")

    def _capabilities(self) -> list[str]:
        if self.hardware is None:
            return ["system.health"]
        return [
            "system.health",
            "power.get_contract",
            "dac.*",
            "xmos.*",
            "led.*",
        ]
