"""Transport contract and failure tests using in-memory buses; no hardware I/O."""
import struct
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

DOOM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOOM_ROOT))
from host.transport import BANK_SIZE, CONTROL, RAM_BASE, ROM_BASE, Chromatic, FrameSender


class Packet:
    def __init__(self, size=4416):
        self.data = bytes(i & 255 for i in range(size))

    def payload(self):
        return self.data


class Mailbox:
    def __init__(self):
        self.ack = 0
        self.buttons = 0
        self.ready = 0x42
        self.writes = []
        self.fail_write = None

    def read(self, address, length):
        assert (address, length) == (RAM_BASE + 16, 16)
        return struct.pack('<HBBH', self.ack, self.buttons, self.ready, 1) + bytes(10)

    def write(self, address, data):
        self.writes.append((address, bytes(data)))
        if len(self.writes) == self.fail_write:
            raise OSError('simulated uncertain USB write')


class FrameSenderTests(unittest.TestCase):
    def setUp(self):
        self.memory = Mailbox()
        self.now = 100.0
        self.sender = FrameSender(self.memory, clock=lambda: self.now, timeout=5)

    def test_payload_precedes_signature_and_commit_and_waits_for_matching_ack(self):
        packet = Packet()
        self.assertTrue(self.sender.poll())
        self.assertTrue(self.sender.send(packet))
        self.assertEqual(self.memory.writes, [
            (RAM_BASE + BANK_SIZE, packet.data),
            (RAM_BASE + 4, b'DOOM' + bytes(8)),
            (RAM_BASE, struct.pack('<HBB', 1, 1, 1)),
        ])
        self.memory.buttons = 0x91
        self.memory.ack = 65535  # Old and unrelated acknowledgements cannot unlock a slot.
        self.assertFalse(self.sender.poll())
        self.assertEqual(self.sender.buttons, 0x91)
        self.assertFalse(self.sender.send(packet))
        self.assertEqual(len(self.memory.writes), 3)
        self.memory.ack = 1
        self.assertTrue(self.sender.poll())
        self.assertTrue(self.sender.send(packet))
        self.assertEqual(self.memory.writes[-3][0], RAM_BASE + 2 * BANK_SIZE)
        self.assertEqual(self.memory.writes[-1], (RAM_BASE, struct.pack('<HBB', 2, 2, 1)))
        self.assertTrue(all(address != RAM_BASE + 16 for address, _ in self.memory.writes),
                        'host must never overwrite the receiver-owned acknowledgement line')

    def test_sequence_wrap_skips_zero_without_breaking_bank_alternation(self):
        self.sender.sequence = 65534
        for sequence, slot in ((65535, 1), (1, 2), (2, 1)):
            self.assertTrue(self.sender.send(Packet()))
            self.assertEqual(self.memory.writes[-1],
                             (RAM_BASE, struct.pack('<HBB', sequence, slot, 1)))
            self.memory.ack = sequence
            self.assertTrue(self.sender.poll())

    def test_ack_deadline_and_receiver_not_ready_fail_without_writing(self):
        self.sender.send(Packet())
        writes = list(self.memory.writes)
        self.now += 4.99
        self.assertFalse(self.sender.poll())
        self.now += 0.02
        with self.assertRaises(TimeoutError):
            self.sender.poll()
        self.assertEqual(self.memory.writes, writes)
        self.memory.ready = 0
        with self.assertRaises(RuntimeError):
            self.sender.poll()
        self.assertEqual(self.memory.writes, writes)

    def test_invalid_payload_does_not_consume_sequence_or_write_memory(self):
        for size in (0, 4415, 4417):
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.sender.send(Packet(size))
        self.assertEqual(self.memory.writes, [])
        self.sender.send(Packet())
        self.assertEqual(self.memory.writes[-1], (RAM_BASE, b'\x01\x00\x01\x01'))

    def test_read_failure_or_receiver_lost_ready_blocks_future_writes(self):
        for failure in ('usb', 'not ready'):
            with self.subTest(failure=failure):
                memory = Mailbox()
                sender = FrameSender(memory)
                if failure == 'usb':
                    memory.read = Mock(side_effect=OSError('lost connection'))
                    expected = OSError
                else:
                    memory.ready = 0
                    expected = RuntimeError
                with self.assertRaises(expected):
                    sender.poll()
                with self.assertRaises(RuntimeError):
                    sender.send(Packet())
                self.assertEqual(memory.writes, [])

    def test_uncertain_write_latches_failure_and_cannot_be_retried(self):
        for fail_write in (1, 2, 3):
            with self.subTest(fail_write=fail_write):
                memory = Mailbox()
                memory.fail_write = fail_write
                sender = FrameSender(memory)
                with self.assertRaises(OSError):
                    sender.send(Packet())
                writes = list(memory.writes)
                # Even a subsequently matching ACK cannot prove what happened
                # during the failed USB operation. Require a new inspected session.
                memory.ack = 1
                with self.assertRaises(RuntimeError):
                    sender.poll()
                with self.assertRaises(RuntimeError):
                    sender.send(Packet())
                self.assertEqual(memory.writes, writes)


def valid_rom():
    data = bytearray(32768)
    data[0x143] = 0xC0
    data[0x147:0x14A] = bytes([0x1B, 0, 4])
    checksum = 0
    for value in data[0x134:0x14D]:
        checksum = (checksum - value - 1) & 255
    data[0x14D] = checksum
    data[0x14E:0x150] = (sum(data) & 65535).to_bytes(2, 'big')
    return data


class FakeRemoteClient:
    """LiteX-shaped memory bus, including its default-zero receive failure."""
    instances = []
    initial_control = 0
    initial_status = 13
    receive_results = None
    fail_upload = False
    corrupt_rom_read = False

    def __init__(self, **kwargs):
        self.__class__.instances.append(self)
        self.opened = self.closed = False
        self.control = self.initial_control
        self.control_writes = []
        self.memory_writes = []
        self.memory_reads = []
        self.memory = {}
        self.receive_results = list(self.receive_results or [])
        self.regs = SimpleNamespace(
            vcart_csr_control=SimpleNamespace(read=lambda: self.read(0), write=self.write_control),
            debug_ctrl_status=SimpleNamespace(read=lambda: self.read(4)),
        )

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def receive_packet(self, socket, addr_size):
        return self.receive_results.pop(0) if self.receive_results else b'received'

    def read(self, address, length=None):
        # Exactly the dangerous LiteX fallback the strict subclass must prevent:
        # a failed read must not masquerade as an inactive virtual cartridge.
        if self.receive_packet(None, 4) == 0:
            return 0 if length is None else [0] * length
        if address == 0:
            return self.control
        if address == 4:
            return self.initial_status
        self.memory_reads.append((address, length))
        values = [self.memory.get(address + i * 4, 0) for i in range(length or 1)]
        if self.corrupt_rom_read and address == ROM_BASE:
            values[0] ^= 1
        return values[0] if length is None else values

    def write(self, address, values):
        self.memory_writes.append((address, list(values)))
        if self.fail_upload:
            raise OSError('simulated uncertain upload')
        for index, value in enumerate(values):
            self.memory[address + 4 * index] = value

    def write_control(self, value):
        self.control = value
        self.control_writes.append(value)
        if value == CONTROL | 1:
            self.memory[RAM_BASE + 16] = 0x42000000  # Receiver's ready byte.


class ChromaticTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.csr = Path(self.directory.name) / 'csr.csv'
        self.rom = Path(self.directory.name) / 'receiver.gbc'
        self.csr.write_text('fixture CSR map; fake bus never accesses hardware\n')
        self.rom.write_bytes(valid_rom())
        FakeRemoteClient.instances = []
        FakeRemoteClient.initial_control = 0
        FakeRemoteClient.initial_status = 13
        FakeRemoteClient.receive_results = None
        FakeRemoteClient.fail_upload = False
        FakeRemoteClient.corrupt_rom_read = False
        module = ModuleType('litex')
        module.RemoteClient = FakeRemoteClient
        self.litex = patch.dict(sys.modules, {'litex': module})
        self.litex.start()
        self.addCleanup(self.litex.stop)
        sleep = patch('host.transport.time.sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def connect(self):
        return Chromatic(self.csr, self.rom)

    def test_active_virtual_cartridge_or_hold_is_never_overwritten(self):
        for control in (1, 2, 3, CONTROL | 1, CONTROL | 3):
            with self.subTest(control=control):
                FakeRemoteClient.initial_control = control
                with self.assertRaisesRegex(RuntimeError, 'already active'):
                    self.connect()
                bus = FakeRemoteClient.instances[-1]
                self.assertTrue(bus.closed)
                self.assertEqual(bus.control_writes, [])
                self.assertEqual(bus.memory_writes, [])

    def test_read_timeout_cannot_masquerade_as_inactive_session(self):
        FakeRemoteClient.initial_control = CONTROL | 1
        FakeRemoteClient.receive_results = [b'valid status response', 0]
        with self.assertRaises(TimeoutError):
            self.connect()
        bus = FakeRemoteClient.instances[-1]
        self.assertTrue(bus.closed)
        self.assertEqual(bus.control_writes, [])
        self.assertEqual(bus.memory_writes, [])

    def test_unready_hardware_or_open_menu_prevents_all_writes(self):
        for status in (0, 1, 4, 5, 7, 15):
            with self.subTest(status=status):
                FakeRemoteClient.initial_status = status
                with self.assertRaises(RuntimeError):
                    self.connect()
                bus = FakeRemoteClient.instances[-1]
                self.assertTrue(bus.closed)
                self.assertEqual(bus.control_writes, [])
                self.assertEqual(bus.memory_writes, [])

    def test_corrupt_or_wrong_rom_is_rejected_before_connecting(self):
        for index, value in ((0x143, 0x80), (0x147, 0x19), (0x149, 3),
                             (0x14D, 0), (0x200, 1)):
            with self.subTest(index=index):
                data = valid_rom()
                data[index] = value
                self.rom.write_bytes(data)
                with self.assertRaises(ValueError):
                    self.connect()
        self.assertEqual(FakeRemoteClient.instances, [])

    def test_upload_holds_core_then_starts_only_receiver_and_cleanly_unloads(self):
        device = self.connect()
        bus = device.bus
        self.assertEqual(bus.control_writes, [2, CONTROL | 7, CONTROL | 1])
        self.assertEqual(device.read(ROM_BASE, 32768), bytes(valid_rom()))
        self.assertEqual(device.read(RAM_BASE, 16), bytes(16))
        for address, values in bus.memory_writes:
            self.assertLessEqual(len(values), 64)
            Chromatic._bounds(address, len(values) * 4)
        device.close()
        self.assertEqual(bus.control_writes, [2, CONTROL | 7, CONTROL | 1, 2, 0])
        self.assertTrue(bus.closed)

    def test_uncertain_upload_and_unclean_exit_never_reset_session(self):
        FakeRemoteClient.fail_upload = True
        with self.assertRaises(OSError):
            self.connect()
        bus = FakeRemoteClient.instances[-1]
        self.assertEqual(bus.control_writes, [2])
        self.assertTrue(bus.closed)
        FakeRemoteClient.fail_upload = False
        device = self.connect()
        initial_writes = list(device.bus.control_writes)
        device.close(clean=False)
        self.assertEqual(device.bus.control_writes, initial_writes)
        self.assertTrue(device.bus.closed)

    def test_failed_rom_readback_stops_before_ram_clear_or_core_start(self):
        FakeRemoteClient.corrupt_rom_read = True
        with self.assertRaisesRegex(RuntimeError, 'readback'):
            self.connect()
        bus = FakeRemoteClient.instances[-1]
        self.assertEqual(bus.control_writes, [2])
        self.assertTrue(bus.closed)
        self.assertTrue(all(ROM_BASE <= address < ROM_BASE + 32768
                            for address, _ in bus.memory_writes))

    def test_changed_session_is_not_reset_during_clean_close(self):
        device = self.connect()
        device.bus.control = 1  # Another virtual-cartridge configuration took over.
        initial_writes = list(device.bus.control_writes)
        device.close(clean=True)
        self.assertEqual(device.bus.control_writes, initial_writes)
        self.assertTrue(device.bus.closed)

    def test_psram_alignment_bounds_and_little_endian_chunking(self):
        device = self.connect()
        try:
            original_writes = list(device.bus.memory_writes)
            original_reads = list(device.bus.memory_reads)
            for address, length in ((ROM_BASE - 4, 4), (RAM_BASE - 4, 4),
                                    (ROM_BASE + 32764, 8), (RAM_BASE + 131068, 8),
                                    (RAM_BASE, -4), (RAM_BASE + 1, 4), (RAM_BASE, 3)):
                with self.subTest(address=address, length=length):
                    with self.assertRaises(ValueError):
                        device.read(address, length)
                    if length >= 0:
                        with self.assertRaises(ValueError):
                            device.write(address, bytes(length))
            self.assertEqual(device.bus.memory_writes, original_writes)
            self.assertEqual(device.bus.memory_reads, original_reads)
            data = bytes(range(256)) + bytes(range(12))
            device.write(RAM_BASE + BANK_SIZE, data)
            self.assertEqual(device.bus.memory_writes[-2][1][0], 0x03020100)
            self.assertEqual([len(values) for _, values in device.bus.memory_writes[-2:]], [64, 3])
            self.assertEqual(device.read(RAM_BASE + BANK_SIZE, len(data)), data)
            self.assertEqual(device.read(RAM_BASE + BANK_SIZE, 4), data[:4])
        finally:
            device.close(clean=False)


if __name__ == '__main__':
    unittest.main()
