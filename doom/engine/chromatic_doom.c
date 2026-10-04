/* SPDX-License-Identifier: GPL-2.0-or-later
 * Chromatic Doom host adapter, 2026-10-04.
 * The original game simulation and rendering remain in doomgeneric.
 */
#include "chromatic_doom.h"
#include "doomgeneric.h"

#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define KEY_QUEUE_SIZE 512
typedef struct { uint8_t key, pressed; } key_event;
static key_event key_queue[KEY_QUEUE_SIZE];
static unsigned key_read, key_write;
static uint8_t key_state[256], rgb[CD_RGB_BYTES];
static uint32_t clock_ms;
static uint64_t frame_serial;
static jmp_buf api_boundary;
static int in_api, attempted, running, exit_status;
static char error_text[512];

void cd_engine_set_error(const char *message)
{
    snprintf(error_text, sizeof(error_text), "%s", message);
}

/* Engine objects are compiled with -Dexit=cd_engine_exit. Contain Doom's
 * normal quit and fatal-error paths instead of terminating Python. */
_Noreturn void cd_engine_exit(int status)
{
    running = 0;
    exit_status = status == 0 ? 1 : -1;
    if (status != 0 && !error_text[0])
        snprintf(error_text, sizeof(error_text), "Doom exited with status %d", status);
    if (in_api)
        longjmp(api_boundary, 1);
    abort(); /* Internal misuse: no engine work is allowed outside an API call. */
}

static char *copy_arg(const char *value)
{
    size_t size = strlen(value) + 1;
    char *copy = malloc(size);
    if (copy)
        memcpy(copy, value, size);
    return copy;
}

int cd_create(const char *iwad_path, int argc, const char *const *argv)
{
    /* The 2 MiB zone is sufficient for the original shareware levels; it is
     * also a useful budget for future embedded builds. The host library
     * currently deliberately has no audio backend. */
    const char *defaults[] = {"chromatic-doom", "-iwad", iwad_path,
                             "-nosound", "-nogui", "-mb", "2"};
    const int default_count = (int)(sizeof(defaults) / sizeof(defaults[0]));
    char **args;
    unsigned char magic[4];
    FILE *wad;
    int i;

    if (attempted) {
        cd_engine_set_error("Only one Doom instance is supported per process; restart the host to reload.");
        return -1;
    }
    if (!iwad_path || argc < 0 || argc > 128 || (argc && !argv)) {
        cd_engine_set_error("Invalid IWAD path or argument list.");
        return -1;
    }
    wad = fopen(iwad_path, "rb");
    if (!wad) {
        cd_engine_set_error("Cannot open the IWAD file.");
        return -1;
    }
    i = fread(magic, 1, sizeof(magic), wad) == sizeof(magic)
        && memcmp(magic, "IWAD", sizeof(magic)) == 0;
    fclose(wad);
    if (!i) {
        cd_engine_set_error("The game data is not an IWAD file.");
        return -1;
    }
    args = calloc((size_t)(argc + default_count + 1), sizeof(*args));
    if (!args) {
        cd_engine_set_error("Cannot allocate the Doom argument list.");
        return -1;
    }
    for (i = 0; i < argc + default_count; ++i) {
        const char *value = i < default_count ? defaults[i] : argv[i - default_count];
        if (!value || !(args[i] = copy_arg(value))) {
            while (i-- > 0)
                free(args[i]);
            free(args);
            cd_engine_set_error("Invalid argument or argument allocation failed.");
            return -1;
        }
    }
    /* Upstream keeps argv pointers for the lifetime of the instance. */
    attempted = 1;
    error_text[0] = '\0';
    in_api = 1;
    if (setjmp(api_boundary)) {
        in_api = 0;
        return exit_status;
    }
    doomgeneric_Create(argc + default_count, args);
    running = 1;
    in_api = 0;
    return 0;
}

int cd_tick(uint32_t elapsed_ms)
{
    if (!running)
        return attempted && exit_status ? exit_status : -1;
    clock_ms += elapsed_ms > 250 ? 250 : elapsed_ms;
    in_api = 1;
    if (setjmp(api_boundary)) {
        in_api = 0;
        return exit_status;
    }
    doomgeneric_Tick();
    in_api = 0;
    return 0;
}

int cd_key(uint8_t key, int pressed)
{
    unsigned next;
    if (!running) {
        cd_engine_set_error("Doom is not running.");
        return -1;
    }
    pressed = !!pressed;
    if (key_state[key] == pressed)
        return 0; /* Suppress host key-repeat and redundant button reports. */
    next = (key_write + 1) % KEY_QUEUE_SIZE;
    if (next == key_read) {
        cd_engine_set_error("Input queue is full; tick the engine before adding more events.");
        return -1;
    }
    key_queue[key_write] = (key_event){key, (uint8_t)pressed};
    key_write = next;
    key_state[key] = (uint8_t)pressed;
    return 0;
}

const uint8_t *cd_framebuffer(void) { return rgb; }
uint64_t cd_frame_serial(void) { return frame_serial; }
const char *cd_error(void) { return error_text; }

void DG_Init(void) {}
void DG_SetWindowTitle(const char *title) { (void)title; }
uint32_t DG_GetTicksMs(void) { return clock_ms; }
void DG_SleepMs(uint32_t ms) { clock_ms += ms ? ms : 1; }

void DG_DrawFrame(void)
{
    for (size_t i = 0; i < CD_WIDTH * CD_HEIGHT; ++i) {
        const uint32_t p = DG_ScreenBuffer[i];
        rgb[3 * i] = (uint8_t)(p >> 16);
        rgb[3 * i + 1] = (uint8_t)(p >> 8);
        rgb[3 * i + 2] = (uint8_t)p;
    }
    ++frame_serial;
}

int DG_GetKey(int *pressed, unsigned char *key)
{
    if (key_read == key_write)
        return 0;
    *pressed = key_queue[key_read].pressed;
    *key = key_queue[key_read].key;
    key_read = (key_read + 1) % KEY_QUEUE_SIZE;
    return 1;
}
