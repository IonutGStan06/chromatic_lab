#include "arcade.h"

/* Pixel positions use 1/16 fixed point; physics never needs floating point. */
int16_t runner_x, runner_y, runner_vy;
uint8_t runner_level, runner_grounded, runner_coins;
static uint8_t coin_taken[96], camera, enemy_clock, enemy_alive;
static uint16_t enemy_x;

static uint8_t terrain(uint8_t x,uint8_t y) {
    if (x>=96 || y>=16) return 0;
    if (y>=14) {
        if ((x>=19 && x<=21) || (x>=40 && x<=43) || (x>=64 && x<=67)) return 0;
        return TILE_GROUND;
    }
    if ((y==11 && ((x>=9 && x<=14)||(x>=30 && x<=36)||(x>=51 && x<=57)||(x>=76 && x<=83))) ||
        (y==8 && ((x>=25 && x<=28)||(x>=60 && x<=63)))) return TILE_BRICK;
    return 0;
}
static uint8_t coin_at(uint8_t x,uint8_t y) {
    if (coin_taken[x]) return 0;
    if ((x%4==2 && y==13 && terrain(x,14)) || (x%3==0 && y==10 && terrain(x,11)) ||
        (x%2==0 && y==7 && terrain(x,8))) return 1;
    return 0;
}
static uint8_t solid(int16_t px,int16_t py) {
    if (px<0 || px>=768) return 1;
    if (py<0 || py>=128) return 0;
    return terrain((uint8_t)(px>>3),(uint8_t)(py>>3))!=0;
}
void runner_init(void) {
    runner_level=1; runner_coins=0; runner_x=24*16; runner_y=96*16;
    runner_vy=0; runner_grounded=0; camera=0; enemy_clock=0; enemy_x=32*8; enemy_alive=1;
    memset(coin_taken,0,96);
}
void runner_tick(void) {
    int16_t px=runner_x>>4, py=runner_y>>4, nx,ny; int8_t speed=0;
    uint8_t tx,ty,old_camera=camera;
    if (keys&J_LEFT) speed=-2;
    if (keys&J_RIGHT) speed=2;
    nx=px+speed;
    if (!solid(nx,py+1) && !solid(nx+7,py+1) && !solid(nx,py+7) && !solid(nx+7,py+7)) runner_x=nx*16;
    px=runner_x>>4;
    if ((pressed&J_A) && runner_grounded) { runner_vy=-66; runner_grounded=0; tone(190); }
    if (!(keys&J_A) && runner_vy<-24) runner_vy=-24;
    runner_vy+=4; if (runner_vy>64) runner_vy=64;
    ny=(runner_y+runner_vy)>>4;
    if (runner_vy>=0 && (solid(px+1,ny+8)||solid(px+6,ny+8))) {
        runner_y=((ny+8)&~7)*16-8*16; runner_vy=0; runner_grounded=1;
    } else if (runner_vy<0 && (solid(px+1,ny)||solid(px+6,ny))) {
        runner_y=((ny+8)&~7)*16; runner_vy=0;
    } else { runner_y+=runner_vy; runner_grounded=0; }
    py=runner_y>>4;
    if (py>128) { finish_game(0); return; }
    tx=(uint8_t)((px+4)>>3); ty=(uint8_t)((py+4)>>3);
    if (tx<96 && coin_at(tx,ty)) { coin_taken[tx]=1; runner_coins++; score+=25; redraw=1; tone(225); }
    enemy_clock++;
    enemy_x=256+(enemy_clock<128 ? enemy_clock/2 : (255-enemy_clock)/2);
    if (enemy_alive && px+7>enemy_x && px<enemy_x+8 && py+7>104 && py<112) {
        if (runner_vy>0 && py<106) { runner_vy=-45; enemy_alive=0; score+=100; redraw=1; }
        else { finish_game(0); return; }
    }
    if (px>=728) { score+=500; finish_game(1); }
    camera=px>72 ? (uint8_t)((px-72)>>3) : 0;
    if (camera>76) camera=76;
    if (camera!=old_camera) redraw=1;
    sprite(0,0,px-(uint16_t)camera*8,py+8);
    if (enemy_alive) sprite(1,1,enemy_x-(uint16_t)camera*8,112); else move_sprite(1,0,0);
}
void runner_draw(void) {
    uint8_t x,y,tx,t;
    text(0,0,"EMBER RUN"); number(13,0,score,5);
    for (y=0;y<16;y++) for (x=0;x<20;x++) {
        tx=camera+x; t=terrain(tx,y);
        if (t) tile(x,y+1,t);
        else if (coin_at(tx,y)) tile(x,y+1,TILE_COIN);
        else if ((tx==91 || tx==92) && y>=9 && y<14) tile(x,y+1,TILE_GATE);
        else if (y==3 && tx%11==0) tile(x,y+1,TILE_STAR);
    }
    sprite(0,0,(runner_x>>4)-(uint16_t)camera*8,(runner_y>>4)+8);
    if (enemy_alive) sprite(1,1,enemy_x-(uint16_t)camera*8,112); else move_sprite(1,0,0);
}
