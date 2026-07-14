#!/usr/bin/env python3
"""Example: animate the Satellite1 LED ring.

A minimal, dependency-light starting point that shows how to drive the ring
with :class:`satellite1.components.led_ring.LedRing`. It is NOT part of the
SDK proper — copy it and make it your own (map animations to your assistant's
listening / speaking / muted states, etc.).

Run on the Pi (needs root for DMA/PWM)::

    sudo python3 examples/led_ring_animations.py           # cycle demos
    sudo python3 examples/led_ring_animations.py --effect rainbow

This is the kind of thing a full "LED animator" service builds on: it watches
your voice-assistant state and picks an effect. Here we just cycle a few so you
can confirm the wiring works.
"""

import argparse
import math
import time

from satellite1.components.led_ring import LedRing, scale, wheel

FPS = 30
GREEN = (0, 255, 0)
BLUE = (0, 90, 255)
ORANGE = (255, 90, 0)


def pulse(ring, color, duration, hz=0.9):
    """Breathe a single colour across the whole ring."""
    end = time.time() + duration
    while time.time() < end:
        t = time.time()
        b = 0.12 + 0.88 * (0.5 * (1.0 + math.sin(2 * math.pi * hz * t)))
        ring.fill(scale(color, b))
        ring.show()
        time.sleep(1.0 / FPS)


def rainbow(ring, duration, speed=0.25):
    """Rotate a rainbow around the ring."""
    n = len(ring)
    end = time.time() + duration
    while time.time() < end:
        t = time.time()
        for i in range(n):
            ring[i] = wheel(int((i * 256 // n) + t * speed * 256) & 0xFF)
        ring.show()
        time.sleep(1.0 / FPS)


EFFECTS = {
    "listening": lambda r, d: pulse(r, GREEN, d),
    "speaking": lambda r, d: pulse(r, BLUE, d),
    "muted": lambda r, d: pulse(r, ORANGE, d),
    "rainbow": lambda r, d: rainbow(r, d),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--effect",
        choices=sorted(EFFECTS),
        help="Run a single effect (default: cycle through all)",
    )
    parser.add_argument("--brightness", type=float, default=0.4)
    parser.add_argument(
        "--seconds", type=float, default=4.0, help="Seconds per effect"
    )
    args = parser.parse_args()

    ring = LedRing.for_satellite1(brightness=args.brightness)
    try:
        effects = [args.effect] if args.effect else sorted(EFFECTS)
        while True:
            for name in effects:
                print(f"effect: {name}")
                EFFECTS[name](ring, args.seconds)
            if args.effect:
                break
    except KeyboardInterrupt:
        pass
    finally:
        ring.clear()


if __name__ == "__main__":
    main()
