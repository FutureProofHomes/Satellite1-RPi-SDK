import pytest

from satellite1_hw.components.ltr303 import LTR303, _calculate_illuminance_lux


@pytest.mark.parametrize(
    ("channel_0", "channel_1", "expected"),
    [
        (1000, 100, (1.7743 * 1000 + 1.1059 * 100) / 200),
        (600, 600, (4.2785 * 600 - 1.9548 * 600) / 200),
        (200, 700, (0.5926 * 200 + 0.1185 * 700) / 200),
        (100, 900, 0.0),
        (0, 0, 0.0),
    ],
)
def test_ltr303_calculates_illuminance_lux(
    channel_0: int, channel_1: int, expected: float
):
    assert _calculate_illuminance_lux(channel_0, channel_1, 2, 100) == pytest.approx(
        expected
    )


def test_ltr303_rounds_illuminance_to_three_decimal_places():
    class Sensor:
        _gain = 2
        _integration_time_ms = 200
        read_illuminance_lux = LTR303.read_illuminance_lux

        def read_channels(self) -> tuple[int, int]:
            return 338, 311

    assert Sensor().read_illuminance_lux() == 2.095
