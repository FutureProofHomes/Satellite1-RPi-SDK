from pathlib import Path

import pytest

import satellite1_cli.cli_xmos as xmos_mod


@pytest.fixture
def requests(monkeypatch):
    calls = []

    def fake_request(args, method, timeout=10.0, **params):
        calls.append((method, params))
        results = {
            "xmos.setup": {"ok": True},
            "xmos.get_firmware": {"firmware": "v1.2.3"},
            "xmos.get_status": {"device_status": 1, "gpio_port_a": 2, "gpio_port_b": 3},
            "xmos.set_mic_output": {"ok": True},
            "xmos.run_spi_test": {"ok": True},
            "xmos.reset": {"ok": True},
            "xmos.enable_flashing": {"ok": True},
            "xmos.disable_flashing": {"ok": True},
            "xmos.flash_firmware": {"ok": True},
        }
        return results[method]

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
        (["setup"], "xmos.setup", {}, "True"),
        (["read-firmware"], "xmos.get_firmware", {}, "v1.2.3"),
        (
            ["read-status"],
            "xmos.get_status",
            {},
            "device_status=0x01 gpio_a=0x02 gpio_b=0x03",
        ),
        (
            ["set-mic-output", "1", "2"],
            "xmos.set_mic_output",
            {"left": 1, "right": 2},
            "True",
        ),
        (["run-spi-test"], "xmos.run_spi_test", {}, "True"),
        (["reset"], "xmos.reset", {}, "True"),
        (["enable-flashing"], "xmos.enable_flashing", {}, "True"),
        (["disable-flashing"], "xmos.disable_flashing", {}, "True"),
        (
            ["flash-firmware", "/tmp/image.bin", "--verify"],
            "xmos.flash_firmware",
            {"path": "/tmp/image.bin", "verify": True},
            "True",
        ),
    ],
)
def test_xmos_commands_use_daemon_rpc(requests, capsys, argv, method, params, output):
    args = build_parser().parse_args(argv)

    assert xmos_mod._handle(args) == 0
    assert requests == [(method, params)]
    assert capsys.readouterr().out.strip() == output
