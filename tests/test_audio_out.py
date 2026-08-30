from types import SimpleNamespace

from satellite1_hw.audio_out import get_active_dac_id


def test_active_dac_uses_line_out_when_jack_is_present():
    assert (
        get_active_dac_id(SimpleNamespace(plugged_in=True), SimpleNamespace())
        == "line-out"
    )


def test_active_dac_uses_speaker_when_line_out_jack_is_absent():
    assert (
        get_active_dac_id(SimpleNamespace(plugged_in=False), SimpleNamespace())
        == "speaker"
    )
