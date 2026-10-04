"""ctypes wrapper around the actual id Software Doom engine."""
import ctypes
import os
import sys
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]


class Doom:
    def __init__(self,wad=None,args=(),state_dir=None):
        suffix='.dylib' if sys.platform=='darwin' else '.so'
        library=ROOT/'engine/build'/('libchromatic_doom'+suffix)
        if not library.exists():
            raise RuntimeError('Build the real Doom engine first: make -C doom/engine')
        self.lib=ctypes.CDLL(str(library))
        self.lib.cd_create.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.POINTER(ctypes.c_char_p)]
        self.lib.cd_create.restype=ctypes.c_int
        self.lib.cd_tick.argtypes=[ctypes.c_uint32]; self.lib.cd_tick.restype=ctypes.c_int
        self.lib.cd_key.argtypes=[ctypes.c_uint8,ctypes.c_int]; self.lib.cd_key.restype=ctypes.c_int
        self.lib.cd_framebuffer.restype=ctypes.POINTER(ctypes.c_uint8)
        self.lib.cd_frame_serial.restype=ctypes.c_uint64
        self.lib.cd_error.restype=ctypes.c_char_p
        wad=Path(wad or ROOT/'engine/data/doom1.wad').resolve()
        if not wad.is_file(): raise FileNotFoundError(wad)
        state_dir=Path(state_dir or default_state_dir()).expanduser().resolve()
        state_dir.mkdir(parents=True,exist_ok=True)
        self.state_dir=state_dir
        self.old_directory=Path.cwd()
        os.chdir(state_dir)
        encoded=[str(a).encode() for a in args]
        argv=(ctypes.c_char_p*len(encoded))(*encoded)
        try: self._result(self.lib.cd_create(os.fsencode(wad),len(encoded),argv))
        except BaseException:
            os.chdir(self.old_directory)
            raise
        self.pressed=set()
        self.finished=False

    def _result(self,value):
        if value<0:
            message=self.lib.cd_error()
            raise RuntimeError(message.decode(errors='replace') if message else 'Doom engine error')
        return value

    def tick(self,elapsed_ms=29):
        self.finished=self._result(self.lib.cd_tick(elapsed_ms))==1
        return not self.finished

    def keys(self,values):
        values=set(values)
        for key in self.pressed-values: self._result(self.lib.cd_key(key,0))
        for key in values-self.pressed: self._result(self.lib.cd_key(key,1))
        self.pressed=values

    @property
    def serial(self): return self.lib.cd_frame_serial()

    def frame(self):
        return np.ctypeslib.as_array(self.lib.cd_framebuffer(),shape=(320*200*3,)).reshape(200,320,3).copy()

    def close(self):
        try:
            if not self.finished: self.keys([])
        finally:
            os.chdir(self.old_directory)


def default_state_dir():
    if sys.platform=='darwin': return Path.home()/'Library/Application Support/Chromatic Doom'
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'chromatic-doom'


# Standard Game Boy joypad bits -> Doom's original keyboard event codes.
GB_KEYS={1:0xae,2:0xac,4:0xad,8:0xaf,16:0xa3,32:0xa2,64:27,128:13}


def gameboy_keys(value):
    return {key for bit,key in GB_KEYS.items() if value&bit}
