# Doom on the host, with an experimental Chromatic display

This adds **the actual Doom engine and original Doom shareware**, including all
nine levels of *Knee-Deep in the Dead*. The engine runs on your Mac or Linux
computer. The handheld route sends its pictures to a Game Boy Color receiver
and sends the Chromatic's buttons back to Doom. Keep the computer connected
while playing. Audio is currently disabled.

Desktop play is available now. The receiver and host components have cloud
tests, but the complete USB path has **not been tested on a physical Chromatic**.
The cloud session cannot access a Chromatic connected to your Mac.

## Play locally

Use Python 3.12, a C compiler and Make. On macOS, the compiler comes with the
Xcode Command Line Tools. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
make -C doom/engine
python doom/play.py
```

The default view previews the image prepared for the handheld. Select any
shareware level, change the window zoom, or compare the original full-color
engine view:

```sh
python doom/play.py --level 3 --scale 3
python doom/play.py --original
```

`--level` accepts 1 through 9. `--scale` changes the window zoom. The engine
retains Doom's original gameplay: monsters, doors, weapons, ammunition,
pickups, menus and maps. Pictures begin at 320×200; the receiver shows a
144×112 viewport inside the Chromatic's 160×144 LCD, using Game Boy Color
tiles and palettes.

| Action | Keyboard | Chromatic |
| --- | --- | --- |
| Move forward/backward | Up/Down or W/S | D-pad Up/Down |
| Turn | Left/Right or A/D | D-pad Left/Right |
| Fire | Ctrl | A |
| Use/open | Space | B |
| Start/confirm | Enter | Start |
| Open menu/back | Escape | Select |

Keyboard extras: Shift runs; comma/period strafe; Tab opens the map; 1–7
select weapons. F10 opens the quit prompt; Y confirms and N cancels. Closing
the desktop window also exits the player.

## Build and check both components

Install [GBDK 4.5.0](https://github.com/gbdk-2020/gbdk-2020/releases/tag/4.5.0)
for the receiver, then set its installation path:

```sh
export GBDK_HOME=/absolute/path/to/gbdk
make doom
make doom-test
```

The host library is built in `doom/engine/build/`; the receiver ROM is
`doom/receiver/build/doom-receiver.gbc`. The receiver ROM is a display/input
client. It contains no Doom engine or Doom game data and needs the host to run.

The engine's independent checks are also available with
`make -C doom/engine check`. They verify the original shareware checksum, boot
all nine levels, compare deterministic frames, exercise turning and firing,
and verify that quitting returns control to the host. Receiver checks exercise
its ROM in PyBoy. Neither test substitutes for a hardware test of the USB and
virtual-cartridge connection.

## Experimental handheld connection

This route requires the third-party **ChromatiX virtual-cartridge firmware**,
whose USB debug bridge exposes virtual cartridge SRAM to the host. The
inspected interface is pinned to
[`enjoy-digital/chromatix` at `0adf3822613a0230d18e0d73193f78337d1100b6`](https://github.com/enjoy-digital/chromatix/tree/0adf3822613a0230d18e0d73193f78337d1100b6).
Use the `chromatix-vcart` design and the matching `csr.csv` from that exact
build. The official plugin's ordinary GB/GBC live-demo transport does not
provide this host framebuffer interface.

Changing the handheld's FPGA firmware is a separate local deployment step.
Use the Chromatic plugin's `modretro-chromatic:chromatic-deployment` skill to
inspect the connected unit. Prepare and verify a backup of its current image,
review the exact candidate firmware and restoration procedure, and obtain
explicit local confirmation before writing firmware. The build and desktop
preview commands above do not perform that write.

After the matching firmware is installed and its debug serial port has been
identified locally, run LiteX's server in one terminal. Replace the example
device path with the verified port:

```sh
python -m pip install -r doom/requirements-transport.txt
litex_server --uart --uart-port /dev/cu.YOUR_CHROMATIC_DEBUG_PORT \
  --bind-ip 127.0.0.1 --bind-port 1234
```

In another terminal, from this repository with its Python environment active:

```sh
python doom/play.py --connect --csr-csv /absolute/path/to/matching/csr.csv \
  --host 127.0.0.1 --port 1234
```

This connection loads the receiver into the virtual cartridge and exchanges
frames and button state through SRAM. It does not flash a game cartridge.
The LiteX Python package and `litex_server` come from the matching ChromatiX
setup; follow its pinned upstream instructions when preparing that environment.
Hardware frame rate and responsiveness still require measurement on the unit.
The player refuses to replace an already-active virtual cartridge: save and
unload that session first. A normal player exit unloads only its own receiver.
After a connection failure it leaves device state untouched for inspection.

An optional test simulates the actual upstream virtual-cart cache RTL using
Migen and LiteX. Clone the pinned ChromatiX checkout above, install
`doom/requirements-transport.txt`, then run from the repository root:

```sh
CHROMATIX_SOURCE=/absolute/path/to/chromatix python -m unittest \
  discover -s doom/tests -p test_vcart_cache.py -v
```

Without `CHROMATIX_SOURCE`, the normal suite explicitly skips this optional
test. The completed cloud RTL run and end-to-end emulator evidence are recorded
in [the published validation report](../docs/doom-validation.json).

Use [the local Mac handoff](LOCAL-MAC-HANDOFF.md) to continue in a local Codex
chat. The [receiver protocol](receiver/README.md) documents the SRAM layout,
frame acknowledgement and cache behavior.

## Source and licensing

The [host engine](engine/README.md) is the GPL Doom source port `doomgeneric`,
pinned to `dcb7a8dbc7a16ce3dda29382ac9aae9d77d21284`, with a small host adapter.
Its corresponding source and GPL license are included. Original gameplay code
is preserved; the integration supplies video, input, timing and host-safe quit.

`doom/engine/data/doom1.wad` is the unmodified Doom v1.9 shareware IWAD, with
SHA256 `1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771`.
Its [redistribution permission](engine/data/SHAREWARE-PERMISSION.txt) is included.
The game data remain copyrighted by id Software and have a separate license
from the engine. Commercial Doom IWADs are not included.

The independent receiver is original MIT-licensed code. ChromatiX retains its
own per-file licenses and GPL requirements for its built FPGA image. Doom,
Game Boy and Chromatic belong to their respective trademark owners; this
project is unaffiliated.
