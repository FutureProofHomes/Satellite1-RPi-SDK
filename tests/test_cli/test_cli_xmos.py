from pathlib import Path

import pytest

import satellite1_cli.cli_xmos as xmos_mod
from satellite1 import XmosStatus


@pytest.fixture
def requests(monkeypatch):
    calls = []

    class FakeXmos:
        async def get_firmware(self):
            calls.append(("get_firmware", {}))
            return "v1.2.3"

        async def get_status(self):
            calls.append(("get_status", {}))
            return XmosStatus(1, 2, 3)

        async def reset(self):
            calls.append(("reset", {}))

        async def flash_firmware(self, path, verify):
            calls.append(("flash_firmware", {"path": path, "verify": verify}))
            return True

    class FakeSatellite:
        xmos = FakeXmos()

    async def fake_request(args, operation):
        return await operation(FakeSatellite())

    monkeypatch.setattr(xmos_mod, "_request", fake_request)
    return calls


def build_parser():
    parser = xmos_mod.argparse.ArgumentParser(prog="sat1-xmos")
    parser.add_argument("--socket", type=Path, default=Path("/tmp/satellite1d.sock"))
    xmos_mod.attach_to_parser(parser)
    return parser


@pytest.mark.parametrize(
    ("argv", "method", "params", "output"),
    [
        (["read-firmware"], "get_firmware", {}, "v1.2.3"),
        (
            ["read-status"],
            "get_status",
            {},
            "device_status=0x01 gpio_a=0x02 gpio_b=0x03",
        ),
        (["reset"], "reset", {}, "True"),
        (
            ["flash-firmware", "/tmp/image.bin", "--verify"],
            "flash_firmware",
            {"path": Path("/tmp/image.bin"), "verify": True},
            "True",
        ),
    ],
)
def test_xmos_commands_use_the_public_client(
    requests, capsys, argv, method, params, output
):
    args = build_parser().parse_args(argv)

    assert xmos_mod._handle(args) == 0
    assert requests == [(method, params)]
    assert capsys.readouterr().out.strip() == output
