import asyncio
import json
from pathlib import Path
from uuid import uuid4

from satellite1d.server import Satellite1dServer


async def _request(socket_path: Path, payload: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(json.dumps(payload).encode() + b"\n")
    await writer.drain()
    response = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    return response


def _socket_path() -> Path:
    return Path("/tmp") / f"s1d-{uuid4().hex}.sock"


def test_server_reports_protocol_capabilities():
    async def run() -> None:
        socket_path = _socket_path()
        server = Satellite1dServer(socket_path=socket_path)
        await server.start()
        try:
            response = await _request(socket_path, {"id": 1, "method": "hello"})
            assert response["id"] == 1
            assert response["result"]["service"] == "satellite1d"
            assert response["result"]["protocol_version"] == 1
        finally:
            await server.close()

    asyncio.run(run())


def test_server_rejects_unknown_methods():
    async def run() -> None:
        socket_path = _socket_path()
        server = Satellite1dServer(socket_path=socket_path)
        await server.start()
        try:
            response = await _request(socket_path, {"id": "x", "method": "nope"})
            assert response == {
                "id": "x",
                "error": {
                    "code": "method_not_found",
                    "message": "unsupported method: nope",
                },
            }
        finally:
            await server.close()

    asyncio.run(run())


def test_server_routes_hardware_requests():
    class FakeHardware:
        async def health(self):
            return {"status": "healthy", "dac": True, "xmos": True}

        async def dispatch(self, method, params):
            assert method == "dac.get_volume"
            assert params == {"dac": "speaker"}
            return {"volume": 0.5}

    async def run() -> None:
        socket_path = _socket_path()
        server = Satellite1dServer(FakeHardware(), socket_path)
        await server.start()
        try:
            response = await _request(
                socket_path,
                {"id": 1, "method": "dac.get_volume", "params": {"dac": "speaker"}},
            )
            assert response == {"id": 1, "result": {"volume": 0.5}}
        finally:
            await server.close()

    asyncio.run(run())


def test_server_routes_firmware_flash_from_socket_group():
    class FakeHardware:
        async def dispatch(self, method, params):
            assert method == "xmos.flash_firmware"
            assert params == {"path": "/tmp/firmware.bin", "verify": True}
            return {"ok": True}

    async def run() -> None:
        socket_path = _socket_path()
        server = Satellite1dServer(FakeHardware(), socket_path)
        await server.start()
        try:
            response = await _request(
                socket_path,
                {
                    "id": 1,
                    "method": "xmos.flash_firmware",
                    "params": {"path": "/tmp/firmware.bin", "verify": True},
                },
            )
            assert response == {"id": 1, "result": {"ok": True}}
        finally:
            await server.close()

    asyncio.run(run())
