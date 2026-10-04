#!/usr/bin/env python3
"""Exercise the exact receiver ROM with PyBoy's public banked cartridge RAM API.

PyBoy tests the GB firmware, not ChromatiX's separate PSRAM cache or USB path.
"""
from pathlib import Path
import hashlib
import struct
import sys
from pyboy import PyBoy

ROM = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'build/doom-receiver.gbc'


def run():
    rom = ROM.read_bytes()
    assert len(rom) == 32768
    assert rom[0x143] == 0xC0, 'CGB-only header'
    assert rom[0x147] == 0x1B, 'MBC5 + RAM + battery'
    assert rom[0x149] == 4, '128 KiB cartridge RAM'
    header = 0
    for byte in rom[0x134:0x14D]:
        header = (header - byte - 1) & 255
    assert header == rom[0x14D]
    assert (sum(rom) - rom[0x14E] - rom[0x14F]) & 65535 == int.from_bytes(rom[0x14E:0x150], 'big')
    p = PyBoy(str(ROM), window='null', sound_emulated=False, cgb=True)
    p.set_emulation_speed(0)
    try:
        def advance_until(predicate, budget=240):
            for _ in range(budget):
                p.tick(1)
                if predicate():
                    return
            raise AssertionError('Receiver did not reach expected state')

        def ack():
            return p.memory[0, 0xA010] | p.memory[0, 0xA011] << 8

        def request(sequence, slot, version=1, magic=b'DOOM'):
            p.memory[0, 0xA000:0xA008] = list(struct.pack('<HBB4s', sequence, slot, version, magic))

        def payload(slot, color):
            # Every tile is solid palette index 1. Indexed attributes vary by tile
            # so all eight palettes and tile-map attribute writes are exercised.
            p.memory[slot, 0xA000:0xAFC0] = list(bytes([255, 0] * 8) * 252)
            p.memory[slot, 0xB000:0xB0FC] = [i % 8 for i in range(252)]
            colors = [0, color, 0, 0] * 8
            p.memory[slot, 0xB100:0xB140] = list(struct.pack('<32H', *colors))

        advance_until(lambda: p.memory[0, 0xA013] == 0x42)
        initial_lcdc = p.memory[0xFF40]
        assert initial_lcdc & 0x80 and not initial_lcdc & 0x20
        initial_heartbeat = p.memory[0, 0xA014] | p.memory[0, 0xA015] << 8
        p.button_press('a')
        p.button_press('up')
        p.tick(3)
        assert p.memory[0, 0xA012] & 0x14 == 0x14
        p.button_release('a')
        p.button_release('up')
        p.tick(3)
        assert p.memory[0, 0xA012] == 0
        assert initial_heartbeat != p.memory[0, 0xA014] | p.memory[0, 0xA015] << 8

        for version, magic, slot in [(2, b'DOOM', 1), (1, b'NOPE', 1), (1, b'DOOM', 3)]:
            request(1, slot, version, magic)
            p.tick(4)
            assert ack() == 0
            assert p.memory[0xFF40] == initial_lcdc

        payload(1, 0x001F)  # Red in CGB RGB555.
        request(1, 1)
        old_ack, frames = ack(), 0
        while ack() != 1 and frames < 180:
            p.tick(1)
            assert p.memory[0xFF40] & 0x80, 'LCD must stay enabled during reception'
            frames += 1
        assert ack() == 1
        assert old_ack == 0
        assert p.memory[0xFF40] == initial_lcdc ^ 0x48
        assert bytes(p.memory[1, 0x8000:0x8FC0]) == bytes([255, 0] * 8) * 252
        assert bytes(p.memory[0, 0x8000:0x8FC0]) == bytes(4032)
        # Newly visible map 9C00 chooses VRAM tile bank 1 and host palettes 0..7.
        for x in range(18):
            addr = 0x9C00 + 2 * 32 + 1 + x
            assert p.memory[0, addr] == x
            assert p.memory[1, addr] == 8 | x % 8
        p.tick(2)
        first = tuple(p.screen.ndarray[20, 12, :3])
        assert first[0] > 200 and first[1] < 30 and first[2] < 30, first
        p.screen.image.save(str(ROM.with_name('receiver-red.png')))

        # New sequence reusing the current slot violates the cache contract.
        request(2, 1)
        p.tick(5)
        assert ack() == 1
        request(1, 2)  # Already acknowledged sequence also ignored.
        p.tick(5)
        assert ack() == 1

        payload(2, 0x03E0)  # Green; second frame must flip back to the first map.
        request(65535, 2)
        advance_until(lambda: ack() == 65535)
        assert p.memory[0xFF40] == initial_lcdc
        assert bytes(p.memory[0, 0x8000:0x8FC0]) == bytes([255, 0] * 8) * 252
        p.tick(2)
        second = tuple(p.screen.ndarray[20, 12, :3])
        assert second[1] > 200 and second[0] < 30 and second[2] < 30, second
        p.screen.image.save(str(ROM.with_name('receiver-green.png')))
        payload(1, 0x7C00)
        request(0, 1)  # Sequence wrap with independently alternating slots.
        advance_until(lambda: ack() == 0)
        assert p.memory[0xFF40] == initial_lcdc ^ 0x48
        p.tick(2)
        third = tuple(p.screen.ndarray[20, 12, :3])
        assert third[2] > 200 and third[0] < 30 and third[1] < 30, third
        p.screen.image.save(str(ROM.with_name('receiver-blue.png')))
        print(f'PASS: header/checksums, boot, joypad/heartbeat, invalid messages, map flips, RGB frames, same-slot rejection, sequence wrap; first frame {frames} video frames')
        print(f'{ROM}: {len(rom)} bytes, sha256 {hashlib.sha256(rom).hexdigest()}')
    finally:
        p.stop(save=False)


if __name__ == '__main__':
    run()
