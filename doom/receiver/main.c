/* SPDX-License-Identifier: MIT
 * ChromatiX virtual-cartridge receiver. Doom itself runs on the host.
 */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>

#define VIEW_X 1u
#define VIEW_Y 2u
#define VIEW_W 18u
#define VIEW_H 14u
#define TILE_COUNT 252u
#define SRAM ((volatile uint8_t *)0xA000u)
#define ATTR_OFFSET 0x1000u
#define PALETTE_OFFSET 0x1100u
#define READY 0x42u

static uint8_t row[20];
static uint8_t attributes[TILE_COUNT];
static palette_color_t colors[32];
static uint8_t header[8];
static uint8_t tile_buffer[256];
static uint8_t display_bank;
static uint8_t last_slot;
static uint16_t acknowledged;
static uint16_t heartbeat;
static volatile uint8_t eviction_read;
static volatile uint8_t dma_keys;

/* Reserved tile 252 D, 253 O, 254 M, 255 blank, duplicated in both VRAM banks. */
static const uint8_t title_tiles[64] = {
    0x00,0x00, 0x78,0x78, 0x44,0x44, 0x44,0x44,
    0x44,0x44, 0x44,0x44, 0x78,0x78, 0x00,0x00,
    0x00,0x00, 0x38,0x38, 0x44,0x44, 0x44,0x44,
    0x44,0x44, 0x44,0x44, 0x38,0x38, 0x00,0x00,
    0x00,0x00, 0x44,0x44, 0x6c,0x6c, 0x54,0x54,
    0x44,0x44, 0x44,0x44, 0x44,0x44, 0x00,0x00,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
};
static const uint8_t title_map[4] = {252, 253, 253, 254};

/* Bank zero's host line [0,15] and device line [16,31] never share a cache line. */
static void publish_status(void) {
    uint8_t keys = joypad();
    SWITCH_RAM_MBC5(0);
    SRAM[0x10] = (uint8_t)acknowledged;
    SRAM[0x11] = (uint8_t)(acknowledged >> 8);
    SRAM[0x12] = keys;
    SRAM[0x13] = READY;
    ++heartbeat;
    SRAM[0x14] = (uint8_t)heartbeat;
    SRAM[0x15] = (uint8_t)(heartbeat >> 8);
}

static void poll_header(void) {
    uint8_t i;
    /* The virtual cartridge caches 256 direct-mapped 16-byte lines. A read of
     * bank 3 offset 0 evicts bank 0 offset 0 before polling the host mailbox.
     * volatile makes the read mandatory even though its value is unused. */
    SWITCH_RAM_MBC5(3);
    eviction_read = SRAM[0];
    SWITCH_RAM_MBC5(0);
    for (i = 0; i != sizeof(header); ++i) header[i] = SRAM[i];
}

static void initialize_display(void) {
    uint8_t i, y, bank;
    uint16_t j;
    DISPLAY_OFF;
    HIDE_WIN;
    HIDE_SPRITES;
    /* Window stays disabled; its map-selection bit addresses the back map. */
    LCDC_REG = LCDCF_BGON | LCDCF_BG8000 | LCDCF_BG9800 | LCDCF_WIN9C00;
    SCX_REG = SCY_REG = 0;
    for (i = 0; i != 32; ++i) colors[i] = RGB(0,0,0);
    colors[3] = RGB(31,16,4);
    set_bkg_palette(0, 8, colors);
    for (bank = 0; bank != 2; ++bank) {
        VBK_REG = bank;
        for (j = 0; j != sizeof(tile_buffer); ++j) tile_buffer[j] = 0;
        for (i = 0; i < 240; i += 16) set_bkg_data(i, 16, tile_buffer);
        set_bkg_data(240, 12, tile_buffer);
        set_bkg_data(252, 4, title_tiles);
    }
    VBK_REG = 0;
    for (i = 0; i != sizeof(row); ++i) row[i] = 255;
    for (y = 0; y != 18; ++y) {
        set_bkg_tiles(0, y, 20, 1, row);
        set_win_tiles(0, y, 20, 1, row);
    }
    set_bkg_tiles(8, 0, 4, 1, title_map);
    set_win_tiles(8, 0, 4, 1, title_map);
    for (y = 0; y != VIEW_H; ++y) {
        for (i = 0; i != VIEW_W; ++i) row[i] = y * VIEW_W + i;
        set_bkg_tiles(VIEW_X, VIEW_Y + y, VIEW_W, 1, row);
        set_win_tiles(VIEW_X, VIEW_Y + y, VIEW_W, 1, row);
    }
    VBK_REG = 1;
    for (i = 0; i != sizeof(row); ++i) row[i] = 0;
    for (y = 0; y != 18; ++y) {
        set_bkg_tiles(0, y, 20, 1, row);
        set_win_tiles(0, y, 20, 1, row);
    }
    for (i = 0; i != VIEW_W; ++i) row[i] = 8;
    for (y = 0; y != VIEW_H; ++y)
        set_win_tiles(VIEW_X, VIEW_Y + y, VIEW_W, 1, row);
    VBK_REG = 0;
    display_bank = 0;
    SHOW_BKG;
    DISPLAY_ON;
}

static void transfer_tiles(uint8_t source_hi, uint8_t destination_hi, uint8_t blocks_minus_one) {
    /* Start outside HBlank (Pan Docs requirement). SRAM and VRAM bank registers
     * must remain unchanged until the final HBlank block completes. */
    while ((STAT_REG & 3) == 0) {}
    HDMA1_REG = source_hi;
    HDMA2_REG = 0;
    HDMA3_REG = destination_hi;
    HDMA4_REG = 0;
    HDMA5_REG = HDMA5F_MODE_HBL | blocks_minus_one;
    while (!(HDMA5_REG & HDMA5F_BUSY)) dma_keys = joypad();
}

static void receive_frame(uint8_t slot, uint16_t sequence) {
    uint8_t i;
    uint8_t target_bank = display_bank ^ 1;
    uint16_t offset, color;
    /* Every accepted frame must alternate SRAM slots. Reading all 252 tile
     * lines in each slot replaces all cache indices used by the preceding
     * slot. Attributes and palettes reuse those indices. Therefore no line
     * from this slot can survive until its next accepted use. */
    SWITCH_RAM_MBC5(slot);
    VBK_REG = target_bank;
    /* Two HBlank transfers: 128 + 124 blocks of 16 bytes. Do not publish status
     * here: that would switch SRAM banks while DMA is using the payload. */
    transfer_tiles(0xA0, 0x00, 127);
    transfer_tiles(0xA8, 0x08, 123);
    SWITCH_RAM_MBC5(slot);
    for (i = 0; i != TILE_COUNT; ++i)
        attributes[i] = (SRAM[ATTR_OFFSET + i] & 7) | (target_bank << 3);
    for (i = 0; i != 32; ++i) {
        offset = PALETTE_OFFSET + ((uint16_t)i << 1);
        color = SRAM[offset];
        color |= (uint16_t)SRAM[offset + 1] << 8;
        colors[i] = color & 0x7fff;
    }
    /* Update only the disabled window's map: this is the next BG map. */
    VBK_REG = 1;
    set_win_tiles(VIEW_X, VIEW_Y, VIEW_W, VIEW_H, attributes);
    VBK_REG = 0;
    wait_vbl_done();
    set_bkg_palette(0, 8, colors);
    LCDC_REG ^= LCDCF_BG9C00 | LCDCF_WIN9C00;
    display_bank = target_bank;
    /* Acknowledge only after a complete scanout of the newly selected map. */
    wait_vbl_done();
    acknowledged = sequence;
    last_slot = slot;
    publish_status();
}

void main(void) {
    uint8_t slot;
    uint16_t sequence;
    if (_cpu != CGB_TYPE) {
        DISPLAY_OFF;
        for (;;) wait_vbl_done();
    }
    cpu_fast();
    ENABLE_RAM_MBC5;
    acknowledged = heartbeat = 0;
    last_slot = 0;
    initialize_display();
    publish_status();
    for (;;) {
        poll_header();
        sequence = header[0] | ((uint16_t)header[1] << 8);
        slot = header[2];
        if ((slot == 1 || slot == 2) && slot != last_slot &&
            header[3] == 1 && header[4] == 'D' && header[5] == 'O' &&
            header[6] == 'O' && header[7] == 'M' && sequence != acknowledged)
            receive_frame(slot, sequence);
        else {
            publish_status();
            wait_vbl_done();
        }
    }
}
