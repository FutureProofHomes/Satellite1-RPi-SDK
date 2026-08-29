from satellite1d.led_patterns.jack import jack_plugged_frames, jack_unplugged_frames


def test_jack_plugged_animation_expands_from_led_zero():
    frames = jack_plugged_frames((1, 2, 3))

    assert len(frames) == 13
    assert frames[0].pixels[0] == (1, 2, 3)
    assert frames[1].pixels[1] == (1, 2, 3)
    assert frames[1].pixels[23] == (1, 2, 3)
    assert frames[-1].pixels[12] == (1, 2, 3)


def test_jack_unplugged_animation_expands_from_led_twelve():
    frames = jack_unplugged_frames((1, 2, 3))

    assert len(frames) == 13
    assert frames[0].pixels[12] == (1, 2, 3)
    assert frames[1].pixels[11] == (1, 2, 3)
    assert frames[1].pixels[13] == (1, 2, 3)
    assert frames[-1].pixels[0] == (1, 2, 3)
