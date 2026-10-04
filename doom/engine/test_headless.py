#!/usr/bin/env python3
"""Exercise the real Doom engine through public input/framebuffer APIs only."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parent
WAD = ROOT / "data" / "doom1.wad"
WAD_SHA256 = "1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771"
WIDTH, HEIGHT = 320, 200


def open_engine(path: Path):
    engine = ctypes.CDLL(str(path))
    engine.cd_create.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                 ctypes.POINTER(ctypes.c_char_p)]
    engine.cd_create.restype = ctypes.c_int
    engine.cd_tick.argtypes = [ctypes.c_uint32]
    engine.cd_tick.restype = ctypes.c_int
    engine.cd_key.argtypes = [ctypes.c_uint8, ctypes.c_int]
    engine.cd_key.restype = ctypes.c_int
    engine.cd_framebuffer.restype = ctypes.POINTER(ctypes.c_uint8)
    engine.cd_frame_serial.restype = ctypes.c_uint64
    engine.cd_error.restype = ctypes.c_char_p
    return engine


def check_ok(engine, result):
    if result != 0:
        raise AssertionError(f"engine status {result}: {engine.cd_error().decode()}")


def snapshot(engine):
    return ctypes.string_at(engine.cd_framebuffer(), WIDTH * HEIGHT * 3)


def save_png(path: Path, pixels: bytes):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = b"".join(b"\0" + pixels[y * WIDTH * 3:(y + 1) * WIDTH * 3]
                    for y in range(HEIGHT))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def worker(args):
    engine = open_engine(args.library)
    assert engine.cd_create(b"/missing-doom-iwad", 0, None) == -1
    argv = (ctypes.c_char_p * 5)(b"-warp", b"1", str(args.level).encode(), b"-skill", b"3")
    with tempfile.TemporaryDirectory(prefix="chromatic-doom-test-") as state:
        os.chdir(state)
        check_ok(engine, engine.cd_create(os.fsencode(WAD), len(argv), argv))
        for _ in range(35):
            check_ok(engine, engine.cd_tick(29))
        initial = snapshot(engine)
        if args.worker == "turn":
            check_ok(engine, engine.cd_key(0xae, 1))
        elif args.worker == "fire":
            check_ok(engine, engine.cd_key(0xa3, 1))
        for _ in range(35):
            check_ok(engine, engine.cd_tick(29))
        pixels = snapshot(engine)
        if args.worker == "quit":
            check_ok(engine, engine.cd_key(0x80 + 0x44, 1))  # F10: original quit prompt.
            for _ in range(3):
                check_ok(engine, engine.cd_tick(29))
            check_ok(engine, engine.cd_key(0x80 + 0x44, 0))
            check_ok(engine, engine.cd_key(ord("y"), 1))
            status = 0
            for _ in range(5):
                status = engine.cd_tick(29)
                if status:
                    break
            assert status == 1, "Doom must return quit without exiting its host"
        if args.output:
            args.output.write_bytes(pixels)
        result = {
            "level": f"E1M{args.level}", "scenario": args.worker,
            "frames": engine.cd_frame_serial(),
            "initial_sha256": hashlib.sha256(initial).hexdigest(),
            "final_sha256": hashlib.sha256(pixels).hexdigest(),
            "colors": len(set(zip(pixels[0::3], pixels[1::3], pixels[2::3]))),
        }
        assert result["frames"] >= 70 and result["colors"] > 32
        print("RESULT " + json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--worker", choices=["idle", "turn", "fire", "quit"])
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.library = args.library.resolve()
    if args.output:
        args.output = args.output.resolve()
    if args.worker:
        worker(args)
        return
    assert hashlib.sha256(WAD.read_bytes()).hexdigest() == WAD_SHA256
    output_dir = args.library.parent
    results = []
    frames = {}
    scenarios = [("idle", level) for level in range(1, 10)] + [
        ("idle", 1), ("turn", 1), ("fire", 1), ("quit", 1)]
    with tempfile.TemporaryDirectory(prefix="chromatic-doom-frames-") as temporary:
        for index, (scenario, level) in enumerate(scenarios):
            raw = Path(temporary) / f"{index}.rgb"
            proc = subprocess.run([
                sys.executable, str(Path(__file__).resolve()),
                "--library", str(args.library), "--worker", scenario,
                "--level", str(level), "--output", str(raw)],
                capture_output=True, text=True, timeout=15)
            if proc.returncode:
                raise AssertionError(f"E1M{level} {scenario} failed:\n{proc.stdout}\n{proc.stderr}")
            result = json.loads(next(line[7:] for line in proc.stdout.splitlines()
                                     if line.startswith("RESULT ")))
            results.append(result)
            if level == 1:
                frames[scenario] = raw.read_bytes()
    assert results[0]["final_sha256"] == results[9]["final_sha256"], "Replay must be deterministic"
    assert results[0]["initial_sha256"] == results[10]["initial_sha256"]
    turned = sum(a != b for a, b in zip(frames["idle"][:320 * 160 * 3],
                                      frames["turn"][:320 * 160 * 3]))
    assert turned > 10000, "Right-arrow input must rotate the actual rendered world"
    # Ammo digits live in the left part of the original status bar. Comparing
    # only that area excludes the weapon animation and changing status face.
    def ammo_region(pixels):
        return b"".join(pixels[(y * 320) * 3:(y * 320 + 42) * 3] for y in range(172, 199))
    assert ammo_region(frames["idle"]) != ammo_region(frames["fire"]), "Fire must consume ammunition"
    save_png(output_dir / "doom-e1m1.png", frames["idle"])
    save_png(output_dir / "doom-e1m1-turn.png", frames["turn"])
    save_png(output_dir / "doom-e1m1-fire.png", frames["fire"])
    report = {
        "iwad_sha256": WAD_SHA256,
        "engine_commit": "dcb7a8dbc7a16ce3dda29382ac9aae9d77d21284",
        "checks": ["original shareware checksum", "all nine levels render",
                   "deterministic replay", "turn changes world", "fire consumes ammo",
                   "normal quit returns to host"],
        "scope": "host engine only; no physical Chromatic validation",
        "results": results,
    }
    (output_dir / "headless-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: Doom shareware E1M1–E1M9, deterministic frames, turning, firing, host-safe quit.")
    print(f"Proof: {output_dir / 'headless-report.json'}")


if __name__ == "__main__":
    main()
