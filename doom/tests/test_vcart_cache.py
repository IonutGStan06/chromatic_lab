"""Exercise the *upstream RTL* behind the Doom SRAM mailbox protocol.

This optional integration test needs Migen and LiteX (``pip install migen litex``)
and a checkout of https://github.com/enjoy-digital/chromatix at the revision below:

    CHROMATIX_SOURCE=/path/to/chromatix python -m unittest \
        discover -s doom/tests -p test_vcart_cache.py -v

It simulates upstream VirtualCart/MBC, including their real cache, CDC, fills,
and write-through FSM. A byte-addressed backing-memory model stands in for the
PSRAM arbiter/controller and host writes; it does not simulate USB, firmware,
the Game Boy CPU, or electrical timing. Payload reads visit both ends of every
16-byte cache line in the receiver's tile/attribute/palette order, using DMA
requests for tiles and CPU requests for attributes/palettes. Allow ~90 seconds.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import unittest


CHROMATIX_REVISION = "0adf3822613a0230d18e0d73193f78337d1100b6"
RAM_BASE = 0x780000
BANK_SIZE = 0x2000
PAYLOAD_REGIONS = ((0, 4032), (0x1000, 252), (0x1100, 64))


def load_rtl():
    checkout = os.environ.get("CHROMATIX_SOURCE")
    if not checkout:
        raise unittest.SkipTest("set CHROMATIX_SOURCE to the pinned ChromatiX checkout")
    checkout = Path(checkout).resolve()
    actual = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != CHROMATIX_REVISION:
        raise AssertionError(f"expected ChromatiX {CHROMATIX_REVISION}, found {actual}")
    try:
        import migen
        from litex.gen.sim import passive, run_simulation
    except ImportError as exc:
        raise unittest.SkipTest("install migen and litex for the optional RTL test") from exc
    spec = importlib.util.spec_from_file_location(
        "doom_upstream_vcart", checkout / "chromatix/gateware/vcart.py"
    )
    rtl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rtl)
    return migen, passive, run_simulation, rtl


class VirtualCartCoherenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dependencies = load_rtl()

    def make_simulation(self):
        migen, passive, run_simulation, rtl = self.dependencies

        class MemoryBus(migen.Module):
            def __init__(self):
                # The documented MultiPortRAMCtrl requester port. Using a model
                # here avoids requiring a physical PSRAM PHY or FPGA toolchain.
                self.port = migen.Record([
                    ("request", 1), ("rnw", 1), ("addr", 23), ("din", 16),
                    ("burst_length", 11), ("write_next", 1), ("done", 1),
                    ("dout_valid", 1),
                ])
                self.dout = migen.Signal(16)
                self.submodules.vcart = rtl.VirtualCart(self.port, self.dout, lines=256)
                self.memory = {}
                self.transactions = []

            def host_write(self, bank, offset, payload):
                for i, value in enumerate(payload):
                    self.memory[RAM_BASE + bank * BANK_SIZE + offset + i] = value

            def host_read(self, bank, offset, length):
                return bytes(self.memory.get(RAM_BASE + bank * BANK_SIZE + offset + i, 0)
                             for i in range(length))

            @passive
            def memory_process(self):
                while True:
                    yield self.port.done.eq(0)
                    yield self.port.dout_valid.eq(0)
                    yield
                    if not (yield self.port.request):
                        continue
                    address = yield self.port.addr
                    length = yield self.port.burst_length
                    read = yield self.port.rnw
                    assert address % 2 == 0
                    assert length == (16 if read else 2)
                    self.transactions.append((read, address, length))
                    # Real PSRAM takes time, and cache-line transfers cross from
                    # xclk to hclk. The xclk clock is four times faster here.
                    for _ in range(8):
                        yield
                    if read:
                        for i in range(0, length, 2):
                            value = (self.memory.get(address + i, 0)
                                     | (self.memory.get(address + i + 1, 0) << 8))
                            yield self.dout.eq(value)
                            yield self.port.dout_valid.eq(1)
                            yield
                        yield self.port.dout_valid.eq(0)
                    else:
                        value = yield self.port.din
                        self.memory[address] = value & 255
                        self.memory[address + 1] = value >> 8
                    yield self.port.done.eq(1)
                    yield

            def begin(self):
                yield self.vcart.enable.eq(1)
                yield self.vcart.mbc_type.eq(rtl.MBC_MBC5)
                yield self.vcart.rom_mask.eq(1)
                yield self.vcart.ram_mask.eq(3)
                yield
                for _ in range(1024):
                    if not (yield self.vcart.wait):
                        break
                    yield
                else:
                    raise AssertionError("initial cache flush timed out")
                yield from self.access(0x0000, 0x0A)

            def access(self, address, value=None, dma=False):
                yield self.vcart.a.eq(address)
                yield self.vcart.din.eq(value or 0)
                yield self.vcart.rd.eq(value is None and not dma)
                yield self.vcart.dma.eq(value is None and dma)
                yield self.vcart.wr.eq(value is not None)
                yield
                yield  # Registered cache tags need two address-setup cycles.
                for _ in range(1024):
                    if not (yield self.vcart.wait):
                        break
                    yield
                else:
                    raise AssertionError(f"cartridge access at {address:#x} timed out")
                yield
                result = yield self.vcart.data
                yield self.vcart.rd.eq(0)
                yield self.vcart.dma.eq(0)
                yield self.vcart.wr.eq(0)
                yield
                return result

            def bank(self, number):
                yield from self.access(0x4000, number)

            def read(self, offset, length, dma=False):
                result = bytearray()
                for i in range(length):
                    result.append((yield from self.access(0xA000 + offset + i, dma=dma)))
                return bytes(result)

            def poll(self):
                yield from self.bank(3)
                yield from self.read(0, 1)
                yield from self.bank(0)
                return (yield from self.read(0, 8))

        dut = MemoryBus()

        def run(generator):
            run_simulation(
                dut, {"hclk": generator, "xclk": dut.memory_process()},
                clocks={"hclk": 60, "xclk": 15},
            )

        return dut, run

    def test_metadata_requires_eviction_and_ack_preserves_request(self):
        """Reproduce stale host data, recover it, and verify physical ACK writes."""
        dut, run = self.make_simulation()
        first = b"\x01\x00\x01\x01DOOM"
        second = b"\x02\x00\x02\x01DOOM"
        dut.host_write(0, 0, first)

        def scenario():
            yield from dut.begin()
            yield from dut.bank(0)
            self.assertEqual((yield from dut.read(0, 8)), first)
            dut.host_write(0, 0, second)
            self.assertEqual((yield from dut.read(0, 8)), first,
                             "this fixture must reproduce noncoherent host writes")
            self.assertEqual((yield from dut.poll()), second)
            # The physical memory bus is 16 bits: a concurrent host commit can
            # expose a new sequence with the previous bank. This is why the ROM
            # must reject a request that reuses its last accepted payload bank.
            dut.host_write(0, 0, b"\x03\x00")
            self.assertEqual((yield from dut.poll()), b"\x03\x00\x02\x01DOOM")
            dut.host_write(0, 2, b"\x01\x01")
            third = b"\x03\x00\x01\x01DOOM"
            self.assertEqual((yield from dut.poll()), third)
            # Bytes 0x10..0x15 are owned exclusively by the receiver. Test odd
            # and even byte writes and their cached 16-bit read/modify/write.
            status = b"\x03\x00\xA5\x42\xCD\xAB"
            for i, value in enumerate(status):
                yield from dut.access(0xA010 + i, value)
            self.assertEqual(dut.host_read(0, 0x10, 6), status)
            self.assertEqual(dut.host_read(0, 0, 8), third)
            writes = [address for read, address, length in dut.transactions if not read]
            self.assertEqual(writes, [RAM_BASE + 0x10 + (i & ~1) for i in range(6)])

        run(scenario())

    def test_alternating_full_payload_banks_evict_every_stale_line(self):
        """All payload cache indices refresh, including attributes/palette aliases."""
        dut, run = self.make_simulation()

        def fill(bank, seed):
            for start, length in PAYLOAD_REGIONS:
                dut.host_write(bank, start,
                               bytes((seed + start + i * 37) & 255 for i in range(length)))

        def verify(bank):
            yield from dut.bank(bank)
            for start, length in PAYLOAD_REGIONS:
                for offset in range(start, start + length, 16):
                    end = min(offset + 15, start + length - 1)
                    for position in (offset, end):
                        actual = yield from dut.read(position, 1, dma=(start == 0))
                        self.assertEqual(actual, dut.host_read(bank, position, 1),
                                         f"stale bank {bank}, offset {position:#x}")

        def scenario():
            yield from dut.begin()
            fill(1, 17)
            yield from verify(1)
            # A same-bank host overwrite really is stale: this tile cache line
            # is outside the indices aliased by attributes (0..15) and palettes
            # (16..19). Polling metadata only evicts index 0.
            old = dut.host_read(1, 0x200, 1)
            fill(1, 99)
            yield from dut.poll()
            yield from dut.bank(1)
            self.assertEqual((yield from dut.read(0x200, 1)), old)
            self.assertNotEqual(old, dut.host_read(1, 0x200, 1))
            # Read the other bank in full before reusing bank 1. Physical bank
            # bits change the tag, while index bits 4..11 remain identical.
            fill(2, 131)
            yield from verify(2)
            yield from dut.poll()
            yield from verify(1)
            # The highest tile byte and the partial final attribute line must
            # both have been fetched from the physical addresses used by host.
            fills = {address for read, address, length in dut.transactions if read}
            for bank in (1, 2):
                for start, length in PAYLOAD_REGIONS:
                    for offset in range(start, start + length, 16):
                        self.assertIn(RAM_BASE + bank * BANK_SIZE + offset, fills)

        run(scenario())


if __name__ == "__main__":
    unittest.main()
