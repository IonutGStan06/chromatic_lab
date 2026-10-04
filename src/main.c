#include "arcade.h"

uint8_t canvas[360], previous_canvas[360], row_palettes[20];
uint8_t game_mode, game_over, paused, menu_choice, keys, pressed;
uint8_t redraw;
uint16_t frame_count, score;
static uint16_t rng_state = 0xACE1U;
static uint8_t previous_keys;

static const palette_color_t palettes[] = {
    RGB(30,29,25),RGB(21,25,22),RGB(11,17,18),RGB(3,5,9),
    RGB(30,29,25),RGB(19,29,29),RGB(7,20,25),RGB(3,5,9),
    RGB(30,29,25),RGB(30,24,12),RGB(26,14,5),RGB(3,5,9),
    RGB(30,29,25),RGB(29,18,20),RGB(23,7,14),RGB(3,5,9),
    RGB(30,29,25),RGB(20,18,30),RGB(13,10,23),RGB(3,5,9),
    RGB(30,29,25),RGB(18,28,17),RGB(8,19,13),RGB(3,5,9),
    RGB(30,29,25),RGB(29,21,29),RGB(21,10,24),RGB(3,5,9),
    RGB(30,29,25),RGB(17,23,30),RGB(8,13,23),RGB(3,5,9)
};

void clear_canvas(void) { memset(canvas, ' ', 360); }
void tile(uint8_t x, uint8_t y, uint8_t value) {
    if (x < 20 && y < 18) canvas[(uint16_t)y*20+x] = value;
}
void text(uint8_t x, uint8_t y, const char *value) {
    while (*value && x < 20) tile(x++,y,(uint8_t)*value++);
}
void number(uint8_t x, uint8_t y, uint16_t value, uint8_t width) {
    while (width) { tile(x+--width,y,'0'+value%10); value/=10; }
}
void sprite(uint8_t id, uint8_t art, int16_t x, int16_t y) {
    set_sprite_tile(id,art);
    set_sprite_prop(id,0);
    if (x < -7 || x > 159 || y < -7 || y > 143) move_sprite(id,0,0);
    else move_sprite(id,(uint8_t)(x+8),(uint8_t)(y+16));
}
void hide_sprites(void) {
    uint8_t i; for (i=0;i<40;i++) move_sprite(i,0,0);
}
uint8_t random_byte(void) {
    rng_state = (rng_state>>1)^((0U-(rng_state&1U))&0xB400U);
    return (uint8_t)rng_state;
}
void tone(uint8_t pitch) {
    NR10_REG=0; NR11_REG=0x80; NR12_REG=0xA1;
    NR13_REG=pitch; NR14_REG=0x86;
}
void finish_game(uint8_t won) {
    game_over=won ? 2 : 1; redraw=1; tone(won ? 220 : 30);
}

static void render(void) {
    uint8_t y,x,t; uint16_t offset;
    for (y=0;y<18;y++) {
        offset=(uint16_t)y*20;
        if (memcmp(canvas+offset,previous_canvas+offset,20)) {
            set_bkg_tiles(0,y,20,1,canvas+offset);
            if (_cpu==CGB_TYPE) {
                for (x=0;x<20;x++) {
                    t=canvas[offset+x];
                    row_palettes[x] = (t>=128 && t<135) ? t-127 :
                        (t==TILE_COIN || t==TILE_TARGET || t==TILE_GATE) ? 2 :
                        (t==TILE_CRATE_OK) ? 5 : (t==TILE_SKULL) ? 3 : 0;
                }
                set_bkg_attributes(0,y,20,1,row_palettes);
            }
            memcpy(previous_canvas+offset,canvas+offset,20);
        }
    }
}

static void begin_game(void) {
    game_mode=menu_choice+1; game_over=0; paused=0; score=0; frame_count=0; redraw=1;
    hide_sprites(); tone(180);
    switch (game_mode) {
        case 1: stack_init(); break;
        case 2: runner_init(); break;
        case 3: vault_init(); break;
        case 4: orbit_init(); break;
        case 5: crates_init(); break;
    }
}

static void draw_menu(void) {
    uint8_t i;
    static const char * const names[]={"STACK SHIFT","EMBER RUN","IRON VAULT","ORBIT DRIFT","CRATEWORKS"};
    static const char * const hints[]={"BUILD. CLEAR. REPEAT.","JUMP THE SKY ISLANDS", "A POCKET 3D SHOOTER", "THRUST. SHOOT. DRIFT.", "PUSH EVERY CRATE HOME"};
    clear_canvas();
    text(3,1,"CHROMATIC LAB"); text(4,2,"AFTER HOURS");
    for (i=0;i<5;i++) { text(3,4+i*2,names[i]); tile(1,4+i*2,menu_choice==i ? '>' : ' '); }
    text(0,14,hints[menu_choice]); text(2,16,"A / START : PLAY");
    tile(18,1,TILE_STAR); tile(1,1,TILE_STAR);
}

static void tick_game(void) {
    if (pressed&J_SELECT) { game_mode=0; redraw=1; hide_sprites(); return; }
    if (game_over) {
        if (pressed&J_A) begin_game();
        else if (pressed&J_B) { game_mode=0; redraw=1; hide_sprites(); }
        return;
    }
    if (pressed&J_START) { paused=!paused; redraw=1; }
    if (paused) return;
    switch (game_mode) {
        case 1: stack_tick(); break;
        case 2: runner_tick(); break;
        case 3: vault_tick(); break;
        case 4: orbit_tick(); break;
        case 5: crates_tick(); break;
    }
}
static void draw_game(void) {
    clear_canvas();
    switch (game_mode) {
        case 1: stack_draw(); break;
        case 2: runner_draw(); break;
        case 3: vault_draw(); break;
        case 4: orbit_draw(); break;
        case 5: crates_draw(); break;
    }
    text(0,17,"START PAUSE SEL MENU");
    if (paused || game_over) {
        uint8_t y,x;
        hide_sprites();
        for (y=6;y<11;y++) for (x=1;x<19;x++) tile(x,y,' ');
        text(5,7,paused ? "PAUSED" : game_over==2 ? "YOU DID IT!" : "GAME OVER");
        text(2,9,paused ? "START TO CONTINUE" : "A RETRY  B MENU");
    }
}

void main(void) {
    DISPLAY_OFF;
    set_bkg_data(0,96,font_tiles); set_bkg_data(128,20,art_tiles);
    set_sprite_data(0,11,sprite_tiles);
    BGP_REG=0xE4; OBP0_REG=0xE4; OBP1_REG=0xE4;
    if (_cpu==CGB_TYPE) {
        cpu_fast();
        set_bkg_palette(0,8,palettes); set_sprite_palette(0,1,palettes+4);
        VBK_REG=1; fill_bkg_rect(0,0,32,32,0); VBK_REG=0;
    }
    NR52_REG=0x80; NR50_REG=0x77; NR51_REG=0x11;
    SPRITES_8x8; hide_sprites(); SHOW_BKG; SHOW_SPRITES;
    memset(previous_canvas,255,360);
    game_mode=0; menu_choice=0;
    draw_menu(); render(); DISPLAY_ON;
    while (1) {
        vsync(); keys=joypad(); pressed=keys&~previous_keys; previous_keys=keys;
        if (!game_mode) {
            if (pressed&J_UP) { menu_choice=menu_choice ? menu_choice-1 : 4; redraw=1; }
            if (pressed&J_DOWN) { menu_choice=(menu_choice+1)%5; redraw=1; }
            if (pressed&(J_A|J_START)) { rng_state+=frame_count; begin_game(); }
        } else tick_game();
        if (redraw) {
            if (game_mode) draw_game(); else draw_menu();
            render(); redraw=0;
        }
        if (!paused && !game_over) frame_count++;
    }
}
