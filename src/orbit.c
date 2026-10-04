#include "arcade.h"

int16_t orbit_x, orbit_y, orbit_vx, orbit_vy;
uint8_t orbit_angle, orbit_lives, orbit_wave;
uint8_t orbit_rock_alive[6], orbit_bullet_alive[4];
static int16_t rock_x[6],rock_y[6],bullet_x[4],bullet_y[4];
static int8_t rock_vx[6],rock_vy[6],bullet_vx[4],bullet_vy[4];
static uint8_t fire_clock, invincible;
static const int8_t dx[]={0,16,0,-16},dy[]={-16,0,16,0};

static void draw_ships(void) {
    uint8_t i;
    if (!invincible || (frame_count&4)) sprite(0,2+orbit_angle,orbit_x>>4,orbit_y>>4);
    else move_sprite(0,0,0);
    for (i=0;i<6;i++) {
        if (orbit_rock_alive[i]) sprite(1+i,7,rock_x[i]>>4,rock_y[i]>>4);
        else move_sprite(1+i,0,0);
    }
    for (i=0;i<4;i++) {
        if (orbit_bullet_alive[i]) sprite(7+i,6,bullet_x[i]>>4,bullet_y[i]>>4);
        else move_sprite(7+i,0,0);
    }
}

static void wrap(int16_t *x,int16_t *y) {
    if (*x<0) *x+=160*16; if (*x>=160*16) *x-=160*16;
    if (*y<16*16) *y+=112*16; if (*y>=128*16) *y-=112*16;
}
static uint8_t near(int16_t ax,int16_t ay,int16_t bx,int16_t by,uint8_t radius) {
    int16_t x=(ax-bx)>>4,y=(ay-by)>>4;
    return x<radius && x>-(int16_t)radius && y<radius && y>-(int16_t)radius;
}
static void spawn_wave(void) {
    uint8_t i;
    redraw=1;
    for (i=0;i<6;i++) {
        orbit_rock_alive[i]=i<orbit_wave+2;
        rock_x[i]=(uint16_t)(random_byte()%150)*16;
        rock_y[i]=(i&1) ? 20*16 : 120*16;
        rock_vx[i]=(int8_t)(random_byte()%13)-6;
        rock_vy[i]=(i&1) ? 5+orbit_wave : -5-orbit_wave;
    }
}
void orbit_init(void) {
    orbit_x=80*16; orbit_y=72*16; orbit_vx=0; orbit_vy=0; orbit_angle=0;
    orbit_lives=3; orbit_wave=1; invincible=80; fire_clock=0;
    memset(orbit_bullet_alive,0,4); spawn_wave();
}
void orbit_tick(void) {
    uint8_t i,j,remaining=0;
    if (invincible) invincible--;
    if (fire_clock) fire_clock--;
    if ((pressed&J_LEFT) || ((keys&J_LEFT) && !(frame_count%10))) orbit_angle=(orbit_angle-1)&3;
    if ((pressed&J_RIGHT) || ((keys&J_RIGHT) && !(frame_count%10))) orbit_angle=(orbit_angle+1)&3;
    if (keys&(J_UP|J_B)) {
        orbit_vx+=dx[orbit_angle]/8; orbit_vy+=dy[orbit_angle]/8;
        if (orbit_vx>28) orbit_vx=28; if (orbit_vx<-28) orbit_vx=-28;
        if (orbit_vy>28) orbit_vy=28; if (orbit_vy<-28) orbit_vy=-28;
    }
    if (keys&J_DOWN) { orbit_vx=orbit_vx*7/8; orbit_vy=orbit_vy*7/8; }
    orbit_x+=orbit_vx; orbit_y+=orbit_vy; wrap(&orbit_x,&orbit_y);
    if ((keys&J_A) && !fire_clock) {
        for (i=0;i<4;i++) if (!orbit_bullet_alive[i]) {
            orbit_bullet_alive[i]=1; bullet_x[i]=orbit_x; bullet_y[i]=orbit_y;
            bullet_vx[i]=dx[orbit_angle]*4; bullet_vy[i]=dy[orbit_angle]*4;
            fire_clock=10; tone(180); break;
        }
    }
    for (i=0;i<4;i++) if (orbit_bullet_alive[i]) {
        bullet_x[i]+=bullet_vx[i]; bullet_y[i]+=bullet_vy[i];
        if (bullet_x[i]<0 || bullet_x[i]>=160*16 || bullet_y[i]<16*16 || bullet_y[i]>=128*16) orbit_bullet_alive[i]=0;
    }
    for (i=0;i<6;i++) if (orbit_rock_alive[i]) {
        rock_x[i]+=rock_vx[i]; rock_y[i]+=rock_vy[i]; wrap(&rock_x[i],&rock_y[i]);
        for (j=0;j<4;j++) if (orbit_bullet_alive[j] && near(rock_x[i],rock_y[i],bullet_x[j],bullet_y[j],7)) {
            orbit_rock_alive[i]=0; orbit_bullet_alive[j]=0; score+=50; redraw=1; tone(230); break;
        }
        if (orbit_rock_alive[i] && !invincible && near(rock_x[i],rock_y[i],orbit_x,orbit_y,7)) {
            orbit_lives--; redraw=1; tone(40); invincible=90;
            orbit_x=80*16; orbit_y=72*16; orbit_vx=0; orbit_vy=0;
            if (!orbit_lives) { finish_game(0); return; }
        }
        remaining+=orbit_rock_alive[i];
    }
    if (!remaining) {
        orbit_wave++; score+=200;
        if (orbit_wave>4) finish_game(1); else spawn_wave();
    }
    draw_ships();
}
void orbit_draw(void) {
    uint8_t i;
    text(0,0,"ORBIT DRIFT"); number(14,0,score,5);
    text(0,1,"LIVES"); number(6,1,orbit_lives,1); text(10,1,"WAVE"); number(15,1,orbit_wave,1);
    for (i=0;i<16;i++) tile((i*7+3)%20,3+(i*3)%12,TILE_FLOOR);
    draw_ships();
    text(0,16,"A FIRE B/UP THRUST");
}
