"""Convert the real Doom framebuffer to the receiver's native CGB format."""
from dataclasses import dataclass

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 144, 112
TILE_COUNT = 252
TILE_BYTES = TILE_COUNT * 16
ATTR_OFFSET = 0x1000
PALETTE_OFFSET = 0x1100
PAYLOAD_SIZE = PALETTE_OFFSET + 64

# Eight stable four-color palettes keep frame-to-frame colors consistent.
# Shared black also keeps the viewport's border black in every palette.
PALETTES = np.array([
    [(0,0,0),(56,56,56),(136,136,136),(240,240,232)],
    [(0,0,0),(72,40,24),(136,88,48),(216,168,96)],
    [(0,0,0),(72,8,8),(152,32,24),(248,88,48)],
    [(0,0,0),(24,64,24),(56,112,40),(144,192,80)],
    [(0,0,0),(24,32,80),(64,88,152),(136,184,232)],
    [(0,0,0),(64,48,32),(128,104,72),(216,192,144)],
    [(0,0,0),(64,24,16),(128,64,40),(216,136,88)],
    [(0,0,0),(48,56,40),(104,112,80),(176,184,152)],
],dtype=np.uint8)


@dataclass(frozen=True)
class FramePacket:
    tiles: bytes
    attributes: bytes
    palettes: bytes

    def payload(self):
        assert len(self.tiles)==TILE_BYTES
        assert len(self.attributes)==TILE_COUNT and len(self.palettes)==64
        data=bytearray(PAYLOAD_SIZE)
        data[:TILE_BYTES]=self.tiles
        data[ATTR_OFFSET:ATTR_OFFSET+TILE_COUNT]=self.attributes
        data[PALETTE_OFFSET:PALETTE_OFFSET+64]=self.palettes
        return bytes(data)

    def image(self):
        raw=np.frombuffer(self.tiles,dtype=np.uint8).reshape(TILE_COUNT,8,2)
        shifts=np.arange(7,-1,-1,dtype=np.uint8)
        indices=((raw[:,:,0,None]>>shifts)&1)|(((raw[:,:,1,None]>>shifts)&1)<<1)
        colors=np.frombuffer(self.palettes,dtype='<u2').reshape(8,4)
        rgb=np.stack([(colors&31)<<3,((colors>>5)&31)<<3,((colors>>10)&31)<<3],axis=-1).astype(np.uint8)
        attrs=np.frombuffer(self.attributes,dtype=np.uint8)
        pixels=rgb[attrs[:,None,None],indices]
        return Image.fromarray(pixels.reshape(14,18,8,8,3).transpose(0,2,1,3,4).reshape(HEIGHT,WIDTH,3))


def encode(rgb, dither=True):
    """Preserve Doom's corrected 4:3 aspect ratio, then choose a palette per tile."""
    source=Image.fromarray(np.asarray(rgb,dtype=np.uint8))
    frame=np.zeros((HEIGHT,WIDTH,3),dtype=np.uint8)
    frame[2:110]=np.asarray(source.resize((WIDTH,108),Image.Resampling.BOX))
    pixels=frame.reshape(14,8,18,8,3).transpose(0,2,1,3,4).reshape(TILE_COUNT,64,3).astype(np.int32)
    if dither:
        pattern=np.tile(np.array([[-12,4],[12,-4]],dtype=np.int32),(4,4)).reshape(1,64,1)
        pixels=np.clip(pixels+pattern,0,255)
    delta=pixels[:,None,:,None,:]-PALETTES.astype(np.int32)[None,:,None,:,:]
    # Luminance-sensitive RGB error favors recognizable geometry and sprites.
    distances=(delta*delta*np.array([2,3,1])).sum(axis=-1)
    nearest=distances.argmin(axis=-1)
    errors=distances.min(axis=-1).sum(axis=-1)
    selected=errors.argmin(axis=-1).astype(np.uint8)
    indices=nearest[np.arange(TILE_COUNT),selected].reshape(TILE_COUNT,8,8).astype(np.uint8)
    weights=(1<<np.arange(7,-1,-1)).astype(np.uint16)
    low=((indices&1)*weights).sum(axis=-1).astype(np.uint8)
    high=(((indices>>1)&1)*weights).sum(axis=-1).astype(np.uint8)
    tiles=np.stack((low,high),axis=-1).tobytes()
    rgb5=PALETTES.astype(np.uint16)>>3
    palette_words=rgb5[:,:,0]|(rgb5[:,:,1]<<5)|(rgb5[:,:,2]<<10)
    return FramePacket(tiles,selected.tobytes(),palette_words.astype('<u2').tobytes())
