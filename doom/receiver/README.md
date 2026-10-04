# Doom display receiver for ChromatiX

This original Game Boy Color ROM displays frames rendered by Doom on the computer and returns the handheld's controls. The Doom engine runs on the host. This ROM alone does not contain Doom, its engine, or its game data.

It targets the experimental, open-source **ChromatiX virtual cartridge** interface. It requires the matching `chromatix-vcart` FPGA firmware and its USB debug bridge. It does not work through the official plugin's GB/GBC `live-demo` transport. Building or testing this directory does not install FPGA firmware or write any cartridge.

## Build and test

```sh
make -C doom/receiver GBDK_HOME=/path/to/gbdk
python doom/receiver/validate.py
```

The repository's prepared cloud environment can use:

```sh
make -C doom/receiver
/workspace/.chromatic-tools/venv/bin/python doom/receiver/validate.py
```

Output: `build/doom-receiver.gbc`, 32,768 bytes, CGB-only, MBC5+RAM+battery (type `0x1B`), 128 KiB RAM (header code `0x04`). `validate.py` uses PyBoy's public banked memory API, such as `pyboy.memory[1, 0xA000:0xAFC0] = list(tile_bytes)`, to emulate the host's SRAM writes. No USB or hardware is involved. It checks the ROM headers/checksums, mailbox validation, actual framebuffer colors, both map flips, sequence wrap, joypad and heartbeat. PyBoy does not emulate ChromatiX's PSRAM/cache bridge.

## Display

The viewport is 144×112 pixels: 18×14 tiles at screen tile coordinate `(1,2)`. The two VRAM banks store independent frames. Background maps `0x9800` and `0x9C00` contain tile IDs 0–251; the inactive map selects the other tile bank. The window stays disabled and its map helper writes the inactive background map. At VBlank, the receiver installs the palette and flips both LCDC map-selection bits. Two HBlank DMA transfers copy 128 and 124 blocks directly from the selected SRAM payload to the inactive VRAM bank. The receiver starts each transfer outside HBlank and keeps both bank registers fixed until it finishes. It keeps the LCD enabled during every frame upload. It acknowledges after the new map has completed a full scanout.

Tiles 252–255 hold D, O, M and blank border pixels. Both VRAM banks contain identical copies. Border/title colors share palette 0 with the host's image.

## SRAM protocol version 1

All 16-bit fields use little-endian byte order. The virtual cartridge's physical SRAM starts at PSRAM offset `0x780000`, exposed at host bus address `0x40780000`. SRAM banks are 8,192 bytes. The Game Boy sees the selected bank at `0xA000`.

| Bank | Offset | Data |
| --- | --- | --- |
| 0 | `0x0000` | Host request: sequence `u16`, payload slot `u8` (1 or 2), version `u8` (1), ASCII `DOOM` |
| 0 | `0x0010` | Device response: acknowledged sequence `u16`, raw GBDK joypad `u8`, ready `0x42`, heartbeat `u16` |
| 1 or 2 | `0x0000` | 252 Game Boy tiles, 4,032 bytes; each 8×8 tile uses alternating low/high bitplane bytes per row |
| 1 or 2 | `0x1000` | 252 palette indices, values 0–7; the receiver sets the VRAM-bank attribute itself |
| 1 or 2 | `0x1100` | Eight palettes, four RGB555 colors each; 64 bytes total |
| 3 | `0x0000` | Cache-eviction scratch read; contents ignored |

Joypad bits: Right `0x01`, Left `0x02`, Up `0x04`, Down `0x08`, A `0x10`, B `0x20`, Select `0x40`, Start `0x80`. RGB555 puts red in bits 0–4, green in 5–9, blue in 10–14.

The host must finish writing a payload before committing its request. Wait for the exact acknowledged sequence before reusing any payload. Alternate slots 1 and 2 after every accepted frame, independently of sequence wrap. Either slot is valid first. Initial acknowledged sequence is zero; start with a different sequence. Duplicate sequences, the previous accepted slot, invalid slots, versions, or magic are ignored. The host should initialize the virtual SRAM before the initial ROM load rather than restoring a saved receiver mailbox.

## Cache contract

ChromatiX's virtual cartridge has a direct-mapped cache with 256 lines of 16 bytes. Host PSRAM writes do not invalidate it. The receiver reads SRAM bank 3 offset zero before every host-header poll, then reads bank 0 offset zero. Those addresses share a cache index and have distinct tags, forcing a fresh metadata read.

Frames must alternate payload slots. Each accepted frame reads every cache index 0–251 when loading its 4,032 tile bytes. Attribute and palette accesses occupy indices already included in that set. Thus all cache indices which could retain a previous slot's payload are replaced by the intervening other-slot frame (or by ROM/status accesses), before that previous slot can be accepted again. The receiver rejects same-slot fresh sequences to preserve this invariant. Device status lives on a separate 16-byte cache line, so cached write-through updates cannot overwrite the host request's bytes.

The ROM polls and publishes controls during idle and after each completed frame. During the DMA transfers it samples joypad into WRAM, but does not publish status because doing so would switch the source SRAM bank. The validation run received a frame in four emulated display frames (about 15 updates/second under PyBoy); this excludes host conversion and USB transfer time. Host throughput and physical USB/cache timing require validation on an actual Chromatic. Emulator timing is not a measured hardware frame rate.

Inspected interface: [ChromatiX commit 0adf3822613a0230d18e0d73193f78337d1100b6](https://github.com/enjoy-digital/chromatix/tree/0adf3822613a0230d18e0d73193f78337d1100b6), particularly `chromatix/gateware/vcart.py` and `scripts/chromatic.py`.
