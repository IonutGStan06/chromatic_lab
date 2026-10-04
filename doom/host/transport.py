"""Volatile virtual-cartridge transport for the pinned ChromatiX-vcart firmware.

This module never writes FPGA firmware, flash, or a physical cartridge.
"""
import struct
import time
from pathlib import Path

ROM_BASE=0x40400000
RAM_BASE=0x40780000
BANK_SIZE=0x2000
CONTROL=(5<<4)|(1<<8)|(15<<20)


class StrictReceive:
    """LiteX normally turns an absent read response into zero; reject it."""
    def receive_packet(self,socket,addr_size):
        response=super().receive_packet(socket,addr_size)
        if response==0:
            raise TimeoutError('LiteX read timed out; device state is unknown')
        return response


class FrameSender:
    """One outstanding frame; alternate banks only after presentation ACK."""
    def __init__(self,memory,clock=time.monotonic,timeout=5):
        self.memory=memory
        self.clock=clock
        self.timeout=timeout
        self.sequence=0
        self.slot=2
        self.pending=None
        self.sent_at=0
        self.buttons=0
        self.faulted=False

    def _check(self):
        if self.faulted:
            raise RuntimeError('Display transport faulted; inspect the device before starting a new session')

    def poll(self):
        self._check()
        try:
            data=self.memory.read(RAM_BASE+16,16)
            ack,buttons,ready,heartbeat=struct.unpack_from('<HBBH',data)
            if ready!=0x42:
                raise RuntimeError('Display client is not ready; stop and inspect the virtual cartridge.')
            self.buttons=buttons
            if self.pending is not None:
                if ack==self.pending: self.pending=None
                elif self.clock()-self.sent_at>self.timeout:
                    raise TimeoutError('Chromatic did not acknowledge the frame; reconnect only after inspecting the device.')
            return self.pending is None
        except BaseException:
            self.faulted=True
            raise

    def send(self,packet):
        self._check()
        if self.pending is not None: return False
        payload=packet.payload()
        if len(payload)!=4416: raise ValueError('Unexpected display payload size')
        self.slot=3-self.slot
        self.sequence=(self.sequence+1)&0xffff or 1
        self.pending=self.sequence
        self.sent_at=self.clock()
        try:
            self.memory.write(RAM_BASE+self.slot*BANK_SIZE,payload)
            # Write signature before committing the sequence/slot word.
            self.memory.write(RAM_BASE+4,b'DOOM'+bytes(8))
            self.memory.write(RAM_BASE,struct.pack('<HBB',self.sequence,self.slot,1))
        except BaseException:
            self.faulted=True
            raise
        return True


class Chromatic:
    def __init__(self,csr_csv,rom,host='127.0.0.1',port=1234):
        try: from litex import RemoteClient
        except ImportError as exc:
            raise RuntimeError('Install doom/requirements-transport.txt in the active virtual environment.') from exc
        csr_csv=Path(csr_csv).expanduser().resolve()
        if not csr_csv.is_file(): raise FileNotFoundError(csr_csv)
        data=Path(rom).read_bytes()
        if len(data)!=32768 or data[0x143]!=0xc0 or data[0x147:0x14a]!=bytes([0x1b,0,4]):
            raise ValueError('Expected the CGB-only MBC5 Doom display client, 32 KB with 128 KB SRAM')
        checksum=0
        for b in data[0x134:0x14d]: checksum=(checksum-b-1)&255
        if checksum!=data[0x14d] or ((sum(data)-sum(data[0x14e:0x150]))&65535)!=int.from_bytes(data[0x14e:0x150],'big'):
            raise ValueError('Display client ROM checksum failed')
        class StrictClient(StrictReceive,RemoteClient): pass
        self.bus=StrictClient(host=host,port=port,csr_csv=str(csr_csv))
        self.loaded=False
        self.bus.open()
        try:
            self.control=self.bus.regs.vcart_csr_control
            status=self.bus.regs.debug_ctrl_status.read()
            if status&7!=5: raise RuntimeError('ChromatiX memory/LCD readiness check failed')
            if not status&8: raise RuntimeError('Close the ChromatiX on-screen menu before connecting')
            if self.control.read()&3:
                raise RuntimeError('A virtual cartridge or hold is already active. Save and unload that session before connecting Doom.')
            # Hold the GB core while initializing our own volatile ROM/RAM.
            self.control.write(2)
            self.loaded=True
            self.write(ROM_BASE,data)
            if self.read(ROM_BASE,len(data))!=data:
                raise RuntimeError('Virtual ROM readback differs; stop and inspect the connection')
            self.write(RAM_BASE,bytes(128*1024))
            self.control.write(CONTROL|7)
            time.sleep(.01)
            self.control.write(CONTROL|1)
            deadline=time.monotonic()+10
            while self.read(RAM_BASE+16,4)[3]!=0x42:
                if time.monotonic()>deadline: raise TimeoutError('Doom display client did not boot')
                time.sleep(.02)
        except BaseException:
            # An uncertain USB operation is never retried or reset automatically.
            self.bus.close()
            raise

    def read(self,address,length):
        self._bounds(address,length)
        result=bytearray()
        for offset in range(0,length,256):
            count=min(256,length-offset)//4
            values=self.bus.read(address+offset,count)
            if isinstance(values,int): values=[values]
            result.extend(struct.pack('<'+'I'*count,*values))
        return bytes(result)

    def write(self,address,data):
        self._bounds(address,len(data))
        for offset in range(0,len(data),256):
            chunk=data[offset:offset+256]
            self.bus.write(address+offset,list(struct.unpack('<'+'I'*(len(chunk)//4),chunk)))

    @staticmethod
    def _bounds(address,length):
        if address%4 or length%4 or length<0:
            raise ValueError('PSRAM operations must be aligned to four bytes')
        if not (ROM_BASE<=address<=address+length<=ROM_BASE+32768 or
                RAM_BASE<=address<=address+length<=RAM_BASE+128*1024):
            raise ValueError('Operation outside this display client virtual ROM/RAM')

    def close(self,clean=True):
        try:
            # Reset only the session created here, and only after a clean exit.
            if clean and self.loaded and self.control.read()==(CONTROL|1):
                self.control.write(2)
                time.sleep(.01)
                self.control.write(0)
        finally: self.bus.close()
