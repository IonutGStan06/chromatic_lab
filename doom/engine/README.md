# Original Doom engine

This is the original Doom game through the GPL `doomgeneric` source port, with
the unmodified Doom 1.9 shareware IWAD (the nine levels of *Knee-Deep in the Dead*).
It is a host library for Linux and macOS, not a Game Boy ROM or a standalone
Chromatic firmware image. Rendering and gameplay run on the host computer.

```sh
make -C doom/engine -j4
make -C doom/engine check
```

Only a C compiler, Make and the C standard library are needed to build. The test
requires Python 3. The build produces `build/libchromatic_doom.so` on Linux or
`build/libchromatic_doom.dylib` on macOS. No SDL or graphics development package
is needed by this library. Linux is validated in this repository; the macOS
build is provided but requires testing on a Mac.

The library renders the real Doom world at 320×200 into RGB24. A frontend can
scale this to the Chromatic's 160×144 LCD. Audio is currently disabled; video,
menus, monsters, weapons, pickups, doors and levels use the upstream engine.

## API

See [`chromatic_doom.h`](chromatic_doom.h) for the full C declarations.

| Function | Purpose |
| --- | --- |
| `cd_create(iwad_path, argc, argv)` | Initialize once. Extra options omit argv[0]. For E1M1 use `{"-warp", "1", "1"}`. |
| `cd_tick(elapsed_ms)` | Advance, read queued input and draw. Call around 35 times per second with measured elapsed milliseconds. |
| `cd_key(key, pressed)` | Queue a real key event; 1 is down, 0 is up. Repeated state reports are harmless. |
| `cd_framebuffer()` | Pointer to 192,000 tightly packed RGB bytes, 320 pixels per row, top-left origin. |
| `cd_frame_serial()` | Increments whenever Doom draws; compare to decide whether to copy a frame. |
| `cd_error()` | Description of the last error. |

Create and tick return 0 for success, 1 for a normal in-game quit, and -1 for an
error. Key returns 0 or -1. Calls must remain on one thread. Upstream has global
state, so one process supports one initialization; start another process to
reload. Quit and engine errors return to the API caller instead of calling
the host process's `exit`.

Key codes: arrows `0xad` up, `0xaf` down, `0xac` left, `0xae` right; fire `0xa3`;
use/open `0xa2`; strafe left/right `0xa0`/`0xa1`; run `0xb6`; strafe modifier
`0xb8`; Enter 13; Escape 27; map 9; pause `0xff`; weapon selection ASCII `1`–`7`.
Send key-up events when keys are released.

The engine uses the caller's working directory for configuration and
`.savegame/`. Frontends should select a private app state directory before
initialization and pass an absolute IWAD path. Never change the working
directory from another thread while the engine runs.

The adapter supplies a deterministic millisecond clock. It advances by the
caller's elapsed time and by Doom's internal wait requests. A tick can draw
several frames during the original screen-melt transition; the final image
is available through `cd_framebuffer`. The caller handles real-time pacing.

## Validation

`make check` starts isolated processes and boots every shareware level. It
checks that deterministic input produces deterministic pictures, right-arrow
input changes the world, fire input changes the ammunition display, and the
original F10/Y quit returns to the host. It uses only command-line options,
key events and framebuffer reads; it never modifies player/game memory.

Screenshots and a JSON report are generated in `build/`. These establish host
engine behavior, not physical Chromatic compatibility or performance.

## Source and data provenance

The engine is vendored from
[`ozkl/doomgeneric`](https://github.com/ozkl/doomgeneric/tree/dcb7a8dbc7a16ce3dda29382ac9aae9d77d21284),
commit `dcb7a8dbc7a16ce3dda29382ac9aae9d77d21284`.
Only sources used by the Unix engine and its headers are included.
[`UPSTREAM.json`](UPSTREAM.json) records the original file hashes.
The adapter and engine integration are GPL-2.0-or-later. Upstream source retains
its copyright notices and [`GPL license`](vendor/doomgeneric/LICENSE).

The only edited upstream file is `i_system.c`: quit now invokes the adapter's
contained exit path, and errors expose their message to the host API. The
build renames upstream `exit` calls to `cd_engine_exit`. Engine files otherwise
retain their upstream game logic. Header/source selection is listed in
[`sources.mk`](sources.mk).

`data/doom1.wad` is the unmodified Doom v1.9 **shareware** IWAD, 4,196,020 bytes:

```text
SHA256 1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771
MD5    f0cefca49926d00903cf57551d901abe
```

The downloaded copy comes from
[`useless-crowbars/doom_rv32i`](https://github.com/useless-crowbars/doom_rv32i/blob/d8e8ea6e059601ea7a631d67a814cc5d3c23fc18/src/support/doom1.wad).
The shareware redistribution permission, reproduced in
[`SHAREWARE-PERMISSION.txt`](data/SHAREWARE-PERMISSION.txt), is John Carmack's
October 23, 1999 statement: “The DOOM shareware wad is freely distributable.”
The same notice is preserved by
[`cnlohr/embeddedDOOM`](https://github.com/cnlohr/embeddedDOOM/blob/master/src/support/LICENSE.txt).
The game artwork/data remain copyrighted by id Software and are not relicensed
under the engine's GPL. Commercial Doom/Ultimate Doom/Doom II IWADs are not
included. Doom is a trademark of id Software; this project is unaffiliated.
