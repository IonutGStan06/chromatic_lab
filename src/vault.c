#include "arcade.h"

uint8_t vault_x, vault_y, vault_angle, vault_health, vault_kills, vault_shots, vault_map;
uint8_t vault_enemy_x[4],vault_enemy_y[4],vault_enemy_alive[4];
static uint8_t shot_flash, hurt_clock, depths[20];
static const int8_t dir_x[]={16,15,11,6,0,-6,-11,-15,-16,-15,-11,-6,0,6,11,15};
static const int8_t dir_y[]={0,6,11,15,16,15,11,6,0,-6,-11,-15,-16,-15,-11,-6};
static const char dungeon[]={
    "11111111"
    "10000001"
    "10111001"
    "10001001"
    "10000001"
    "10101001"
    "10000001"
    "11111111"
};

static uint8_t wall(int16_t x,int16_t y) {
    if (x<0 || x>=128 || y<0 || y>=128) return 1;
    return dungeon[(uint8_t)(y>>4)*8+(uint8_t)(x>>4)]=='1';
}
static uint8_t ray_clear(uint8_t x,uint8_t y) {
    int16_t dx=(int16_t)x-vault_x,dy=(int16_t)y-vault_y;
    uint8_t i;
    for (i=1;i<8;i++) if (wall(vault_x+dx*i/8,vault_y+dy*i/8)) return 0;
    return 1;
}
void vault_init(void) {
    uint8_t i;
    static const uint8_t ex[]={40,104,24,88},ey[]={24,72,104,104};
    vault_x=24; vault_y=24; vault_angle=0; vault_health=5; vault_kills=0; vault_shots=0;
    shot_flash=0; hurt_clock=0; vault_map=0;
    for (i=0;i<4;i++) { vault_enemy_x[i]=ex[i]; vault_enemy_y[i]=ey[i]; vault_enemy_alive[i]=1; }
}
static void move_player(int8_t dx,int8_t dy) {
    int16_t x=vault_x+dx,y=vault_y+dy;
    if (!wall(x+2,vault_y) && !wall(x-2,vault_y)) vault_x=x;
    if (!wall(vault_x,y+2) && !wall(vault_x,y-2)) vault_y=y;
}
void vault_tick(void) {
    uint8_t i; int16_t dx,dy,fwd,side; int8_t mx,my;
    if (shot_flash) { shot_flash--; redraw=1; }
    if (hurt_clock) hurt_clock--;
    if (pressed&J_B) { vault_map=!vault_map; redraw=1; }
    if (!(frame_count%5)) {
        if (keys&(J_UP|J_DOWN|J_LEFT|J_RIGHT)) redraw=1;
        if (keys&J_LEFT) vault_angle=(vault_angle-1)&15;
        if (keys&J_RIGHT) vault_angle=(vault_angle+1)&15;
        if (keys&J_UP) move_player(dir_x[vault_angle]/6,dir_y[vault_angle]/6);
        if (keys&J_DOWN) move_player(-dir_x[vault_angle]/6,-dir_y[vault_angle]/6);
    }
    if ((pressed&J_A) || ((keys&J_A) && !(frame_count%12))) {
        vault_shots++; shot_flash=3; redraw=1; tone(35);
        for (i=0;i<4;i++) if (vault_enemy_alive[i]) {
            dx=(int16_t)vault_enemy_x[i]-vault_x; dy=(int16_t)vault_enemy_y[i]-vault_y;
            fwd=(dx*dir_x[vault_angle]+dy*dir_y[vault_angle])/16;
            side=(-dx*dir_y[vault_angle]+dy*dir_x[vault_angle])/16;
            if (fwd>0 && side*4<=fwd && side*4>=-fwd && ray_clear(vault_enemy_x[i],vault_enemy_y[i])) {
                vault_enemy_alive[i]=0; vault_kills++; score+=100; tone(210); break;
            }
        }
    }
    for (i=0;i<4;i++) if (vault_enemy_alive[i]) {
        dx=(int16_t)vault_enemy_x[i]-vault_x; dy=(int16_t)vault_enemy_y[i]-vault_y;
        if (!(frame_count%20)) {
            redraw=1;
            mx=dx>0 ? -1 : dx<0 ? 1 : 0; my=dy>0 ? -1 : dy<0 ? 1 : 0;
            if (!wall(vault_enemy_x[i]+mx,vault_enemy_y[i])) vault_enemy_x[i]+=mx;
            if (!wall(vault_enemy_x[i],vault_enemy_y[i]+my)) vault_enemy_y[i]+=my;
        }
        if (dx<9 && dx>-9 && dy<9 && dy>-9 && !hurt_clock) {
            vault_health--; hurt_clock=50; redraw=1; tone(60);
            if (!vault_health) { finish_game(0); return; }
        }
    }
    if (vault_kills==4 && (vault_x>>4)==6 && (vault_y>>4)==6) { score+=500; finish_game(1); }
}
void vault_draw(void) {
    uint8_t x,y,d,h,top,i,w,cx; int16_t rx,ry,dx,dy,fwd,side;
    text(0,0,"IRON VAULT"); text(0,1,"HP"); number(3,1,vault_health,1);
    text(6,1,"KILLS"); number(12,1,vault_kills,1); text(14,1,"/4");
    if (vault_map) {
        text(4,3,"TACTICAL MAP");
        for (y=0;y<8;y++) for (x=0;x<8;x++) tile(6+x,5+y,dungeon[y*8+x]=='1' ? TILE_WALL : TILE_FLOOR);
        tile(12,11,vault_kills==4 ? TILE_GATE : TILE_GHOST);
        for (i=0;i<4;i++) if (vault_enemy_alive[i]) tile(6+(vault_enemy_x[i]>>4),5+(vault_enemy_y[i]>>4),TILE_SKULL);
        tile(6+(vault_x>>4),5+(vault_y>>4),TILE_HERO);
        text(0,15,"CLEAR ALL THEN EXIT"); text(0,16,"A FIRE B VIEW");
        return;
    }
    for (x=0;x<20;x++) {
        dx=dir_x[vault_angle]-dir_y[vault_angle]*((int8_t)x-10)/12;
        dy=dir_y[vault_angle]+dir_x[vault_angle]*((int8_t)x-10)/12;
        rx=(uint16_t)vault_x*16; ry=(uint16_t)vault_y*16;
        for (d=1;d<96;d++) { rx+=dx; ry+=dy; if (wall(rx>>4,ry>>4)) break; }
        depths[x]=d; h=112/(d+3); if (h>14) h=14; if (!h) h=1;
        top=9-h/2;
        for (y=2;y<16;y++) {
            if (y>=top && y<top+h) tile(x,y,d<24 ? TILE_WALL : TILE_BRICK);
            else if (y>=9) tile(x,y,TILE_FLOOR);
        }
    }
    for (i=0;i<4;i++) if (vault_enemy_alive[i]) {
        dx=(int16_t)vault_enemy_x[i]-vault_x; dy=(int16_t)vault_enemy_y[i]-vault_y;
        fwd=(dx*dir_x[vault_angle]+dy*dir_y[vault_angle])/16;
        side=(-dx*dir_y[vault_angle]+dy*dir_x[vault_angle])/16;
        if (fwd>3) {
            dx=10+side*12/fwd;
            if (dx>=0 && dx<20 && fwd<depths[dx]) {
                cx=dx; h=96/(fwd+3); if (h>8) h=8; if (h<1) h=1;
                w=(h+1)/2; top=9-h/2;
                for (y=0;y<h;y++) for (x=0;x<w;x++) {
                    dx=(int16_t)cx+x-w/2;
                    if (dx>=0 && dx<20) tile(dx,top+y,y==0 ? TILE_SKULL : TILE_BLOCK+2);
                }
            }
        }
    }
    tile(10,9,'+');
    tile(9,14,shot_flash ? TILE_STAR : TILE_GHOST); tile(10,14,shot_flash ? TILE_STAR : TILE_GHOST);
    text(0,16,vault_kills==4 ? "EXIT AT MAP 6 / 6" : "A FIRE B MAP");
    if (vault_kills==4) {
        tile(18,0,TILE_GATE);
        number(16,1,vault_x>>4,1); number(18,1,vault_y>>4,1);
    }
}
