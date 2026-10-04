/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CHROMATIC_DOOM_H
#define CHROMATIC_DOOM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__GNUC__)
#define CD_API __attribute__((visibility("default")))
#else
#define CD_API
#endif

#define CD_WIDTH 320
#define CD_HEIGHT 200
#define CD_RGB_BYTES (CD_WIDTH * CD_HEIGHT * 3)

/* Doom key codes; printable keys, including weapons '1'..'7', use ASCII. */
enum cd_key_code {
    CD_KEY_RIGHT = 0xae, CD_KEY_LEFT = 0xac,
    CD_KEY_UP = 0xad, CD_KEY_DOWN = 0xaf,
    CD_KEY_STRAFE_LEFT = 0xa0, CD_KEY_STRAFE_RIGHT = 0xa1,
    CD_KEY_USE = 0xa2, CD_KEY_FIRE = 0xa3,
    CD_KEY_ESCAPE = 27, CD_KEY_ENTER = 13, CD_KEY_MAP = 9,
    CD_KEY_RUN = 0xb6, CD_KEY_STRAFE = 0xb8, CD_KEY_PAUSE = 0xff
};

/* One instance per process; all calls must run on the same thread. No SDL.
 * argv contains extra Doom options, WITHOUT argv[0], for example
 * {"-warp", "1", "1", "-skill", "3"}. Strings are copied.
 * Returns 0 on success, -1 on failure, or 1 when Doom requests normal exit.
 * Use a private working directory for the engine's config and save files.
 */
CD_API int cd_create(const char *iwad_path, int argc, const char *const *argv);

/* Advance the engine clock (normally 28 or 29 ms at 35 Hz), process queued
 * input and render. Doom may advance its clock further while waiting for
 * its next simulation tic or completing the original screen-melt effect.
 * Values above 250 ms are capped to prevent an unbounded catch-up loop.
 */
CD_API int cd_tick(uint32_t elapsed_ms);
CD_API int cd_key(uint8_t key, int pressed);

/* Stable pointer to RGB24, top-left origin, row-major, tightly packed.
 * Rewritten at every draw; copy before the next cd_tick call.
 */
CD_API const uint8_t *cd_framebuffer(void);
CD_API uint64_t cd_frame_serial(void);
CD_API const char *cd_error(void);

#ifdef __cplusplus
}
#endif
#endif
