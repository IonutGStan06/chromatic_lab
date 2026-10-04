#!/usr/bin/env python3
"""Play the real Doom shareware engine; optionally use a ChromatiX display."""
import argparse
import ctypes
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from host.engine import Doom,gameboy_keys
from host.video import encode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',type=int,choices=range(1,10),default=1)
    parser.add_argument('--scale',type=int,choices=range(1,9),default=4)
    parser.add_argument('--original',action='store_true',help='Display full-resolution Doom on the computer')
    parser.add_argument('--state-dir',type=Path,help='Private config/save directory')
    parser.add_argument('--connect',action='store_true',help='Load volatile display client onto an already-configured ChromatiX-vcart')
    parser.add_argument('--csr-csv',type=Path,help='CSR map matching the installed experimental firmware')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=1234)
    parser.add_argument('--frames',type=int,help='Stop after this many ticks (for automation)')
    parser.add_argument('--screenshot',type=Path,help='Save the final displayed frame')
    options=parser.parse_args()
    if options.connect and not options.csr_csv: parser.error('--connect requires --csr-csv from the installed firmware build')
    if options.frames is not None and options.frames<1: parser.error('--frames must be positive')
    screenshot=options.screenshot.resolve() if options.screenshot else None
    csr=options.csr_csv.resolve() if options.csr_csv else None
    root=Path(__file__).resolve().parent
    import sdl2
    keymap={sdl2.SDLK_RIGHT:0xae,sdl2.SDLK_d:0xae,sdl2.SDLK_LEFT:0xac,sdl2.SDLK_a:0xac,
            sdl2.SDLK_UP:0xad,sdl2.SDLK_w:0xad,sdl2.SDLK_DOWN:0xaf,sdl2.SDLK_s:0xaf,
            sdl2.SDLK_LCTRL:0xa3,sdl2.SDLK_RCTRL:0xa3,sdl2.SDLK_SPACE:0xa2,
            sdl2.SDLK_RETURN:13,sdl2.SDLK_ESCAPE:27,sdl2.SDLK_TAB:9,
            sdl2.SDLK_LSHIFT:0xb6,sdl2.SDLK_COMMA:0xa0,sdl2.SDLK_PERIOD:0xa1,
            sdl2.SDLK_y:ord('y'),sdl2.SDLK_n:ord('n'),sdl2.SDLK_F10:0xc4,
            **{ord(str(i)):ord(str(i)) for i in range(1,8)}}
    keyboard=set()
    device=None; engine=None; window=None; renderer=None; texture=None
    clean=False; pixels=None
    try:
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO|sdl2.SDL_INIT_EVENTS)!=0:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        width,height=(320,200) if options.original else (160,144)
        title=b'DOOM shareware | Host engine | Chromatic display preview | Ctrl fire / Space use'
        window=sdl2.SDL_CreateWindow(title,sdl2.SDL_WINDOWPOS_CENTERED,sdl2.SDL_WINDOWPOS_CENTERED,width*options.scale,height*options.scale,sdl2.SDL_WINDOW_SHOWN)
        if not window: raise RuntimeError(sdl2.SDL_GetError().decode())
        renderer=sdl2.SDL_CreateRenderer(window,-1,sdl2.SDL_RENDERER_SOFTWARE)
        if not renderer: raise RuntimeError(sdl2.SDL_GetError().decode())
        sdl2.SDL_RenderSetLogicalSize(renderer,width,height)
        texture=sdl2.SDL_CreateTexture(renderer,sdl2.SDL_PIXELFORMAT_RGB24,sdl2.SDL_TEXTUREACCESS_STREAMING,width,height)
        if not texture: raise RuntimeError(sdl2.SDL_GetError().decode())
        if options.connect:
            from host.transport import Chromatic,FrameSender
            device=Chromatic(csr,root/'receiver/build/doom-receiver.gbc',options.host,options.port)
            sender=FrameSender(device)
            print('Connected to the experimental display client. Doom runs on this computer.',flush=True)
        engine=Doom(args=['-warp','1',str(options.level),'-skill','3'],state_dir=options.state_dir)
        print('Original Doom shareware: nine levels. Audio is disabled in this build.',flush=True)
        running=True; ticks=0; last_packet=None; next_frame=time.monotonic(); next_video=0
        event=sdl2.SDL_Event()
        while running:
            while sdl2.SDL_PollEvent(ctypes.byref(event)):
                if event.type==sdl2.SDL_QUIT: running=False
                elif event.type==sdl2.SDL_WINDOWEVENT and event.window.event==sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
                    keyboard.clear()
                elif event.type in (sdl2.SDL_KEYDOWN,sdl2.SDL_KEYUP):
                    key=event.key.keysym.sym
                    if key in keymap:
                        if event.type==sdl2.SDL_KEYDOWN: keyboard.add(key)
                        else: keyboard.discard(key)
            if not running: break
            ready=sender.poll() if device else True
            keys={keymap[key] for key in keyboard}
            if device: keys|=gameboy_keys(sender.buttons)
            engine.keys(keys)
            if not engine.tick(29): break
            ticks+=1
            now=time.monotonic()
            # Host simulation stays at 35 Hz. Quantize only for a new display frame.
            if ready and (now>=next_video or last_packet is None):
                last_packet=encode(engine.frame())
                if device: sender.send(last_packet)
                next_video=now+1/15
            if options.original: pixels=engine.frame()
            else:
                pixels=np.zeros((144,160,3),dtype=np.uint8)
                pixels[16:128,8:152]=np.asarray(last_packet.image())
            pixels=np.ascontiguousarray(pixels)
            if sdl2.SDL_UpdateTexture(texture,None,pixels.ctypes.data,width*3)!=0:
                raise RuntimeError(sdl2.SDL_GetError().decode())
            sdl2.SDL_RenderClear(renderer); sdl2.SDL_RenderCopy(renderer,texture,None,None); sdl2.SDL_RenderPresent(renderer)
            if options.frames and ticks>=options.frames: break
            next_frame+=1/35
            delay=next_frame-time.monotonic()
            if delay>0: time.sleep(delay)
            else: next_frame=time.monotonic()
        if screenshot and pixels is not None:
            screenshot.parent.mkdir(parents=True,exist_ok=True)
            Image.fromarray(pixels).save(screenshot)
        clean=True
    finally:
        try:
            if engine: engine.close()
        finally:
            try:
                if device: device.close(clean=clean)
            finally:
                if texture: sdl2.SDL_DestroyTexture(texture)
                if renderer: sdl2.SDL_DestroyRenderer(renderer)
                if window: sdl2.SDL_DestroyWindow(window)
                sdl2.SDL_Quit()


if __name__=='__main__':
    try: main()
    except (RuntimeError,OSError,ValueError,TimeoutError) as exc:
        print(f'Doom: {exc}',file=sys.stderr)
        sys.exit(1)
