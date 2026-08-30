from satellite1d.services.device_info import _strip_hardware_revision


def test_hardware_version_omits_the_board_revision():
    assert _strip_hardware_revision("Raspberry Pi Zero 2 W Rev 1.0") == (
        "Raspberry Pi Zero 2 W"
    )
