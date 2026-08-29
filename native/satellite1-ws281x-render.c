/*
 * Fixed-purpose privileged renderer for the Satellite1 GPIO 12 LED ring.
 * It uses the vendored rpi_ws281x library (BSD-2-Clause, Jeremy Garff).
 */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "ws2811.h"

#define FRAME_SIZE 72
#define LED_COUNT 24
#define GPIO_PIN 12
#define COMPATIBLE_PATH "/proc/device-tree/compatible"

static int read_frame(uint8_t frame[FRAME_SIZE])
{
    size_t offset = 0;
    ssize_t count;
    uint8_t extra;

    while (offset < FRAME_SIZE) {
        count = read(STDIN_FILENO, frame + offset, FRAME_SIZE - offset);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return -1;
        }
        offset += (size_t)count;
    }

    do {
        count = read(STDIN_FILENO, &extra, 1);
    } while (count < 0 && errno == EINTR);
    return count == 0 ? 0 : -1;
}

static int has_bcm2711(void)
{
    uint8_t compatible[512];
    const uint8_t needle[] = "bcm2711";
    ssize_t count;
    size_t index;
    int fd = open(COMPATIBLE_PATH, O_RDONLY | O_CLOEXEC);

    if (fd < 0) {
        return 0;
    }
    count = read(fd, compatible, sizeof(compatible));
    close(fd);
    if (count <= 0) {
        return 0;
    }
    for (index = 0; index + sizeof(needle) - 1 <= (size_t)count; index++) {
        if (memcmp(compatible + index, needle, sizeof(needle) - 1) == 0) {
            return 1;
        }
    }
    return 0;
}

int main(int argc, char *argv[])
{
    uint8_t frame[FRAME_SIZE];
    ws2811_return_t result;
    ws2811_t ledstring = {
        .freq = WS2811_TARGET_FREQ,
        .dmanum = has_bcm2711() ? 10 : 14,
        .channel = {
            [0] = {
                .gpionum = GPIO_PIN,
                .invert = 0,
                .count = LED_COUNT,
                .strip_type = WS2812_STRIP,
                .brightness = 255,
            },
        },
    };

    (void)argv;
    if (argc != 1 || read_frame(frame) != 0) {
        fputs("expected exactly one 72-byte RGB frame on stdin\n", stderr);
        return EXIT_FAILURE;
    }

    result = ws2811_init(&ledstring);
    if (result != WS2811_SUCCESS) {
        fprintf(stderr, "ws2811_init failed: %s\n", ws2811_get_return_t_str(result));
        return EXIT_FAILURE;
    }

    for (size_t index = 0; index < LED_COUNT; index++) {
        size_t offset = index * 3;
        ledstring.channel[0].leds[index] =
            ((uint32_t)frame[offset] << 16) |
            ((uint32_t)frame[offset + 1] << 8) |
            frame[offset + 2];
    }

    result = ws2811_render(&ledstring);
    if (result != WS2811_SUCCESS) {
        fprintf(stderr, "ws2811_render failed: %s\n", ws2811_get_return_t_str(result));
    } else {
        result = ws2811_wait(&ledstring);
        if (result != WS2811_SUCCESS) {
            fprintf(stderr, "ws2811_wait failed: %s\n", ws2811_get_return_t_str(result));
        }
    }
    ws2811_fini(&ledstring);
    return result == WS2811_SUCCESS ? EXIT_SUCCESS : EXIT_FAILURE;
}
