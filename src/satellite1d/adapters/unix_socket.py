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

from .. import SERVICE_NAME
from ..commands import DaemonCommands
from ..contracts.events import (
    ButtonPressed,
    DaemonEvent,
    EventSubscriber,
    LineOutJackChanged,
    MicMuteChanged,
    VolumeChanged,
)

DEFAULT_SOCKET_PATH = Path("/run/satellite1/satellite1d.sock")
log = logging.getLogger(__name__)


class UnixSocketAdapter:
    """Serve local daemon RPC requests."""

    def __init__(
        self,
        commands: DaemonCommands | None = None,
        socket_path: Path = DEFAULT_SOCKET_PATH,
        events: EventSubscriber | None = None,
    ) -> None:
        self.commands = commands
        self.events = events
        self.socket_path = socket_path
        self._server: asyncio.AbstractServer | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._client_writers: set[asyncio.StreamWriter] = set()

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
        for writer in self._client_writers:
            writer.transport.abort()
        client_tasks = tuple(self._client_tasks)
        for task in client_tasks:
            task.cancel()
        if client_tasks:
            await asyncio.gather(*client_tasks, return_exceptions=True)
        if self._server is not None:
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
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        self._client_writers.add(writer)
        cancelled = False
        try:
            while line := await reader.readline():
                try:
                    request = parse_request(json.loads(line))
                except (json.JSONDecodeError, ProtocolError):
                    response = await self._handle_message(line)
                else:
                    if request.method == "events.subscribe":
                        await self._stream_events(
                            reader, request.params, request.request_id, writer
                        )
                        return
                    response = await self._dispatch(
                        request.method, request.params, request.request_id
                    )
                writer.write(
                    json.dumps(response, separators=(",", ":")).encode() + b"\n"
                )
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            self._client_writers.discard(writer)
            if task is not None:
                self._client_tasks.discard(task)
            writer.close()
            if not cancelled:
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass

    async def _stream_events(
        self,
        reader: asyncio.StreamReader,
        params: dict[str, Any],
        request_id: int | str,
        writer: asyncio.StreamWriter,
    ) -> None:
        include_current = params.get("include_current", True)
        if not isinstance(include_current, bool):
            writer.write(
                json.dumps(
                    failure(
                        request_id,
                        "invalid_params",
                        "include_current must be a boolean",
                    )
                ).encode()
                + b"\n"
            )
            await writer.drain()
            return
        if self.commands is None or self.events is None:
            writer.write(
                json.dumps(
                    failure(
                        request_id,
                        "method_not_found",
                        "unsupported method: events.subscribe",
                    )
                ).encode()
                + b"\n"
            )
            await writer.drain()
            return
        try:
            subscriber = self.events.subscribe()
            initial = await self.commands.current_events() if include_current else []
        except Exception as exc:
            writer.write(
                json.dumps(failure(request_id, "hardware_failure", str(exc))).encode()
                + b"\n"
            )
            await writer.drain()
            return
        try:
            writer.write(
                json.dumps(success(request_id, {"subscribed": True})).encode() + b"\n"
            )
            for event in initial:
                writer.write(json.dumps(_event_payload(event), separators=(",", ":")).encode() + b"\n")
            await writer.drain()
            while True:
                event_task = asyncio.create_task(subscriber.get())
                disconnect_task = asyncio.create_task(reader.readline())
                done, pending = await asyncio.wait(
                    {event_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                if disconnect_task in done:
                    return
                event = event_task.result()
                if event is None:
                    return
                writer.write(
                    json.dumps(_event_payload(event), separators=(",", ":")).encode() + b"\n"
                )
                await writer.drain()
        finally:
            self.events.unsubscribe(subscriber)

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
            if self.commands is None:
                return success(request_id, {"status": "healthy"})
            return success(request_id, await self.commands.health())
        if self.commands is None:
            return failure(
                request_id, "method_not_found", f"unsupported method: {method}"
            )
        try:
            return success(request_id, await self.commands.dispatch(method, params))
        except KeyError:
            return failure(
                request_id, "method_not_found", f"unsupported method: {method}"
            )
        except ValueError as exc:
            return failure(request_id, "invalid_params", str(exc))
        except Exception:
            log.exception("hardware operation failed: %s", method)
            return failure(request_id, "hardware_failure", "hardware operation failed")

    def _capabilities(self) -> list[str]:
        if self.commands is None:
            return ["system.health"]
        capabilities = [
            "system.health",
            "power.get_contract",
            "dac.get_volume",
            "dac.set_volume",
            "dac.set_mute",
            "dac.get_plugged_in",
            "dac.get_amp_level",
            "dac.set_amp_level",
            "mics.get_muted",
            "xmos.get_firmware",
            "xmos.get_status",
            "xmos.reset",
            "xmos.flash_firmware",
        ]
        if getattr(self.commands, "led_ring_enabled", False):
            capabilities.extend(("led.render", "led.clear"))
        if self.events is not None:
            capabilities.append("events.subscribe")
        return capabilities


def _event_payload(event: DaemonEvent) -> dict[str, Any]:
    if isinstance(event, ButtonPressed):
        return {"event": "buttons.pressed", "data": {"name": event.name}}
    if isinstance(event, MicMuteChanged):
        return {"event": "mics.muted_changed", "data": {"muted": event.muted}}
    if isinstance(event, VolumeChanged):
        return {
            "event": "audio.volume_changed",
            "data": {"output": event.output, "volume": event.volume},
        }
    if isinstance(event, LineOutJackChanged):
        return {"event": "audio.line_out_jack_changed", "data": {"plugged_in": event.plugged_in}}
    raise TypeError(f"unsupported event: {event!r}")
