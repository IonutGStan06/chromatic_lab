#ifndef ARCADE_H
#define ARCADE_H
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>

#define SCREEN_W 20
#define SCREEN_H 18
#define TILE_BLOCK 128
#define TILE_GHOST 135
#define TILE_GROUND 136
#define TILE_BRICK 137
#define TILE_COIN 138
#define TILE_GATE 139
#define TILE_WALL 140
#define TILE_FLOOR 141
#define TILE_TARGET 142
#define TILE_CRATE 143
#define TILE_CRATE_OK 144
#define TILE_HERO 145
#define TILE_SKULL 146
#define TILE_STAR 147

extern const uint8_t font_tiles[], art_tiles[], sprite_tiles[];
extern uint8_t canvas[360], game_mode, game_over, paused, menu_choice;
extern uint8_t keys, pressed, redraw;
extern uint16_t frame_count, score;

void clear_canvas(void);
void tile(uint8_t x, uint8_t y, uint8_t value);
void text(uint8_t x, uint8_t y, const char *value);
void number(uint8_t x, uint8_t y, uint16_t value, uint8_t width);
void sprite(uint8_t id, uint8_t art, int16_t x, int16_t y);
void hide_sprites(void);
void tone(uint8_t pitch);
uint8_t random_byte(void);
void finish_game(uint8_t won);

void stack_init(void); void stack_tick(void); void stack_draw(void);
void runner_init(void); void runner_tick(void); void runner_draw(void);
void vault_init(void); void vault_tick(void); void vault_draw(void);
void orbit_init(void); void orbit_tick(void); void orbit_draw(void);
void crates_init(void); void crates_tick(void); void crates_draw(void);

#endif
