"""Actual Doom -> CGB quantizer -> compiled receiver ROM end-to-end checks.

This runs a local Game Boy Color emulator. It does not test physical Chromatic
USB transport or FPGA behavior. Generated images contain genuine emulator pixels.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image
from pyboy import PyBoy

DOOM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOOM_ROOT))
from host.engine import Doom, gameboy_keys
from host.video import encode
from host.transport import FrameSender, RAM_BASE, BANK_SIZE

ROM = DOOM_ROOT / 'receiver/build/doom-receiver.gbc'
ARTIFACTS = DOOM_ROOT / 'build'


class PyBoyCartridgeMemory:
    """Same byte-addressed SRAM interface as production transport, backed by PyBoy."""
    def __init__(self, emulator):
        self.emulator = emulator
        self.writes = []

    def _segments(self, address, length):
        if address % 4 or length % 4 or not RAM_BASE <= address <= address + length <= RAM_BASE + 128 * 1024:
            raise ValueError('Invalid aligned virtual cartridge SRAM access')
        offset = address - RAM_BASE
        while length:
            bank, within_bank = divmod(offset, BANK_SIZE)
            size = min(length, BANK_SIZE - within_bank)
            yield bank, 0xA000 + within_bank, size
            offset += size
            length -= size

    def read(self, address, length):
        return b''.join(bytes(self.emulator.memory[bank, start:start + size])
                        for bank, start, size in self._segments(address, length))

    def write(self, address, data):
        self.writes.append((address, len(data)))
        offset = 0
        for bank, start, size in self._segments(address, len(data)):
            self.emulator.memory[bank, start:start + size] = list(data[offset:offset + size])
            offset += size


class DisplayIntegrationTest(unittest.TestCase):
    def test_actual_doom_frames_and_handheld_controls(self):
        self.assertTrue(ROM.is_file(), 'Build the receiver: make -C doom/receiver')
        ARTIFACTS.mkdir(exist_ok=True)
        emulator = PyBoy(str(ROM), window='null', cgb=True, sound_emulated=False)
        emulator.set_emulation_speed(0)
        movie = []
        latencies = []
        memory = PyBoyCartridgeMemory(emulator)
        sender = FrameSender(memory, clock=lambda: emulator.frame_count / 60)
        source_hashes = {str(path.relative_to(DOOM_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted((DOOM_ROOT / 'host').glob('*.py'))}
        library_suffix = '.dylib' if sys.platform == 'darwin' else '.so'
        engine_library = DOOM_ROOT / 'engine/build' / ('libchromatic_doom' + library_suffix)
        engine_sha256 = hashlib.sha256(engine_library.read_bytes()).hexdigest()
        comparisons = 0

        def ack():
            return emulator.memory[0, 0xA010] | emulator.memory[0, 0xA011] << 8

        def until(predicate, frames=240):
            for elapsed in range(1, frames + 1):
                emulator.tick(1)
                if predicate():
                    return elapsed
            self.fail('Receiver did not reach expected state within its frame budget')

        def submit(rgb):
            nonlocal comparisons
            packet = encode(rgb)
            self.assertTrue(sender.poll())
            writes_before = len(memory.writes)
            self.assertTrue(sender.send(packet))
            self.assertEqual(memory.writes[writes_before:], [
                (RAM_BASE + sender.slot * BANK_SIZE, 4416),
                (RAM_BASE + 4, 12), (RAM_BASE, 4)],
                'Production sender must publish the complete payload and signature before committing')
            self.assertFalse(sender.send(packet), 'Only one frame may be outstanding')
            self.assertEqual(len(memory.writes), writes_before + 3)
            elapsed = until(sender.poll)
            self.assertEqual(ack(), sender.sequence)
            latencies.append(elapsed)
            # ACK follows a complete scanout. A further neutral emulator frame
            # also puts screenshots beyond the VBlank where the ACK was posted.
            emulator.tick(1)
            expected = np.asarray(packet.image())
            observed = emulator.screen.ndarray[16:128, 8:152, :3]
            mismatch = np.any(expected != observed, axis=2)
            self.assertEqual(int(mismatch.sum()), 0,
                             f'{mismatch.sum()} receiver pixels differ from the exact encoded frame')
            comparisons += 1
            frame = emulator.screen.image.convert('RGB').copy()
            movie.append(frame.resize((640, 576), Image.Resampling.NEAREST))
            return packet, frame

        def handheld(keys):
            held = getattr(handheld, 'held', set())
            keys = set(keys)
            for key in held - keys:
                emulator.button_release(key)
            for key in keys - held:
                emulator.button_press(key)
            handheld.held = keys
            emulator.tick(2)
            self.assertTrue(sender.poll())
            return sender.buttons

        engine = None
        try:
            until(lambda: emulator.memory[0, 0xA013] == 0x42)
            with tempfile.TemporaryDirectory(prefix='display-state-', dir=ARTIFACTS) as state:
                engine = Doom(args=['-warp', '1', '1', '-skill', '3'], state_dir=state)
                for _ in range(35):
                    self.assertTrue(engine.tick())
                start = engine.frame()
                submit(start)

                right = handheld(['right'])
                self.assertEqual(right, 0x01)
                self.assertEqual(gameboy_keys(right), {0xAE})
                engine.keys(gameboy_keys(right))
                for _ in range(7):
                    for _ in range(2):
                        self.assertTrue(engine.tick())
                    submit(engine.frame())
                turned = engine.frame()
                changed = int(np.any(start[:160] != turned[:160], axis=2).sum())
                self.assertGreater(changed, 5000, 'Physical-button mapping must rotate Doom geometry')
                engine.keys(gameboy_keys(handheld([])))

                # Move through the actual level with the receiver's up button.
                up = handheld(['up'])
                self.assertEqual(up, 0x04)
                engine.keys(gameboy_keys(up))
                for _ in range(12):
                    for _ in range(2):
                        self.assertTrue(engine.tick())
                    submit(engine.frame())
                moved = engine.frame()
                movement_changed = int(np.any(turned[:160] != moved[:160], axis=2).sum())
                self.assertGreater(movement_changed, 2000, 'Up must move through the actual Doom level')
                engine.keys(gameboy_keys(handheld([])))

                ammo_before = engine.frame()[172:199, :42].copy()
                fire = handheld(['a'])
                self.assertEqual(fire, 0x10)
                self.assertEqual(gameboy_keys(fire), {0xA3})
                engine.keys(gameboy_keys(fire))
                for _ in range(14):
                    for _ in range(3):
                        self.assertTrue(engine.tick())
                    packet, screenshot = submit(engine.frame())
                ammo_after = engine.frame()[172:199, :42]
                self.assertFalse(np.array_equal(ammo_before, ammo_after),
                                 'A button must fire the actual Doom weapon and consume ammunition')
                engine.keys(gameboy_keys(handheld([])))
                for _ in range(3):
                    engine.tick()
                packet, screenshot = submit(engine.frame())

                screenshot.save(ARTIFACTS / 'doom-receiver.png')
                screenshot.resize((640, 576), Image.Resampling.NEAREST).save(
                    ARTIFACTS / 'doom-receiver-large.png')
                packet.image().save(ARTIFACTS / 'doom-cgb-viewport.png')
                Image.fromarray(engine.frame()).save(ARTIFACTS / 'doom-host.png')
                movie[0].save(ARTIFACTS / 'doom-receiver.gif', save_all=True,
                              append_images=movie[1:], duration=85, loop=0, disposal=2)
                engine.close()
                engine = None

            report = {
                'scope': 'Actual Doom engine, production FrameSender and compiled CGB receiver in PyBoy; no physical hardware or USB validation',
                'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                'engine_library_sha256': engine_sha256,
                'iwad_sha256': hashlib.sha256((DOOM_ROOT / 'engine/data/doom1.wad').read_bytes()).hexdigest(),
                'host_source_sha256': source_hashes,
                'receiver_source_sha256': hashlib.sha256((DOOM_ROOT / 'receiver/main.c').read_bytes()).hexdigest(),
                'receiver_sha256': hashlib.sha256(ROM.read_bytes()).hexdigest(),
                'exact_pixelwise_frame_comparisons': comparisons,
                'sender_checks': ['payload before commit', 'single outstanding frame', 'ACK clears pending', 'production input decoding'],
                'final_emulator_png_sha256': hashlib.sha256((ARTIFACTS / 'doom-receiver.png').read_bytes()).hexdigest(),
                'final_encoded_viewport_sha256': hashlib.sha256(np.asarray(packet.image()).tobytes()).hexdigest(),
                'viewport': {'x': 8, 'y': 16, 'width': 144, 'height': 112},
                'turn_changed_world_pixels': changed,
                'movement_changed_world_pixels': movement_changed,
                'input_checks': ['Right turns', 'Up moves', 'A fires and reduces ammo'],
                'receiver_emulated_frame_latencies': latencies,
                'gif_note': 'Genuine 160x144 emulator frames enlarged 4x with nearest-neighbor; edited presentation timing, no fake handheld panel',
            }
            (ARTIFACTS / 'display-report.json').write_text(json.dumps(report, indent=2) + '\n')
            self.assertGreaterEqual(comparisons, 30)
            self.assertLessEqual(max(latencies), 6,
                                 'Receiver should normally sustain at least 10 emulated updates/second')
        finally:
            if engine is not None:
                engine.close()
            emulator.stop(save=False)


if __name__ == '__main__':
    unittest.main()
