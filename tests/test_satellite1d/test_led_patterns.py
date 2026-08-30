from satellite1d.led_patterns.jack import jack_plugged_frames, jack_unplugged_frames
from satellite1d.led_patterns.lva import (
    pulse_frames,
    rotating_blob_frames,
    thinking_frames,
    timer_tick_frames,
    twinkle_frames,
)


def test_jack_plugged_animation_expands_from_led_zero():
    animation = jack_plugged_frames((1, 2, 3), frame_interval=0.04)
    frames = animation.frames

    assert len(frames) == 13
    assert animation.frame_interval == 0.04
    assert frames[0].pixels[0] == (1, 2, 3)
    assert frames[1].pixels[1] == (1, 2, 3)
    assert frames[1].pixels[23] == (1, 2, 3)
    assert frames[-1].pixels[12] == (1, 2, 3)


def test_jack_unplugged_animation_expands_from_led_twelve():
    frames = jack_unplugged_frames((1, 2, 3), frame_interval=0.04).frames

    assert len(frames) == 13
    assert frames[0].pixels[12] == (1, 2, 3)
    assert frames[1].pixels[11] == (1, 2, 3)
    assert frames[1].pixels[13] == (1, 2, 3)
    assert frames[-1].pixels[0] == (1, 2, 3)


def test_lva_rotating_blob_has_two_trailing_opposing_blobs():
    animation = rotating_blob_frames((100, 80, 60), speed=1.0)
    frames = animation.frames

    assert len(frames) == 24
    assert animation.frame_interval == 0.05
    assert frames[0].pixels[0] == (100, 80, 60)
    assert frames[0].pixels[23] == (75, 60, 45)
    assert frames[0].pixels[22] == (50, 40, 30)
    assert frames[0].pixels[12] == (100, 80, 60)
    assert frames[0].pixels[11] == (75, 60, 45)
    assert frames[0].pixels[10] == (50, 40, 30)
    assert frames[1].pixels[1] == (100, 80, 60)


def test_lva_rotating_blob_supports_half_and_reverse_speeds():
    slow_frames = rotating_blob_frames((100, 80, 60), speed=0.5).frames
    reverse_frames = rotating_blob_frames((100, 80, 60), speed=-1.0).frames

    assert len(slow_frames) == 48
    assert slow_frames[0] == slow_frames[1]
    assert slow_frames[2].pixels[1] == (100, 80, 60)
    assert reverse_frames[1].pixels[23] == (100, 80, 60)


def test_lva_rotating_blob_caps_bright_microphone_positions():
    frame = rotating_blob_frames((255, 255, 255), speed=1.0).frames[0]

    assert frame.pixels[0] == (128, 128, 128)
    assert frame.pixels[12] == (128, 128, 128)
    assert frame.pixels[23] == (192, 192, 192)


def test_lva_thinking_pulses_opposing_pixels():
    frames = thinking_frames((100, 80, 60)).frames

    assert len(frames) == 20
    assert frames[0].pixels[2] == (98, 78, 58)
    assert frames[0].pixels[14] == (98, 78, 58)
    assert frames[10].pixels[2] == (0, 0, 0)
    assert frames[11].pixels[2] == (9, 7, 5)
    assert frames[0].pixels[0] == (0, 0, 0)


def test_lva_pulse_and_twinkle_frames_are_full_ring_and_red():
    pulse = pulse_frames((255, 0, 0))
    twinkle = twinkle_frames((255, 0, 0))

    assert len(pulse.frames) == 20
    assert pulse.frames[0].pixels == ((250, 0, 0),) * 24
    assert pulse.frames[10].pixels == ((0, 0, 0),) * 24
    assert len(twinkle.frames) == 24
    assert set(twinkle.frames[0].pixels) == {(255, 0, 0), (0, 0, 0)}


def test_lva_timer_tick_shows_remaining_arc_and_moving_dip():
    frames = timer_tick_frames((100, 80, 60), total_seconds=60, seconds_left=30).frames

    assert len(frames) == 24
    assert frames[0].pixels[0] == (89, 71, 53)
    assert frames[1].pixels[0] == (100, 80, 60)
    assert frames[0].pixels[11] == (100, 80, 60)
    assert frames[0].pixels[12] == (0, 0, 0)
