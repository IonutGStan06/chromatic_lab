#include "arcade.h"

uint8_t stack_board[140], stack_piece, stack_rotation, stack_next, stack_lines;
int8_t stack_x, stack_y;
static uint8_t drop_clock, bag[7], bag_index;
/* Four occupied coordinates per orientation, packed as x | (y << 2). */
static const uint8_t shapes[7][4][4]={
    {{4,5,6,7},{2,6,10,14},{4,5,6,7},{2,6,10,14}},
    {{1,2,5,6},{1,2,5,6},{1,2,5,6},{1,2,5,6}},
    {{4,5,6,9},{1,4,5,9},{1,4,5,6},{1,5,6,9}},
    {{0,4,5,6},{1,2,5,9},{4,5,6,10},{1,5,8,9}},
    {{2,4,5,6},{1,5,9,10},{4,5,6,8},{0,1,5,9}},
    {{1,2,4,5},{1,5,6,10},{1,2,4,5},{1,5,6,10}},
    {{0,1,5,6},{2,5,6,9},{0,1,5,6},{2,5,6,9}}
};
static uint8_t fits(int8_t x,int8_t y,uint8_t r) {
    uint8_t i,c; int8_t bx,by;
    for (i=0;i<4;i++) {
        c=shapes[stack_piece][r][i]; bx=x+(c&3); by=y+(c>>2);
        if (bx<0 || bx>=10 || by>=14) return 0;
        if (by>=0 && stack_board[(uint8_t)by*10+bx]) return 0;
    }
    return 1;
}
static uint8_t bag_draw(void) {
    uint8_t i,j,t;
    if (bag_index==7) {
        for (i=0;i<7;i++) bag[i]=i;
        for (i=6;i;i--) { j=random_byte()%(i+1); t=bag[i]; bag[i]=bag[j]; bag[j]=t; }
        bag_index=0;
    }
    return bag[bag_index++];
}
static void spawn(void) {
    stack_piece=stack_next; stack_next=bag_draw();
    stack_x=3; stack_y=-1; stack_rotation=0; drop_clock=0; redraw=1;
    if (!fits(stack_x,stack_y,stack_rotation)) finish_game(0);
}
void stack_init(void) {
    memset(stack_board,0,140); stack_lines=0; bag_index=7;
    stack_next=bag_draw(); spawn();
}
static void lock_piece(void) {
    uint8_t x,y,i,c,full,cleared=0; int8_t row; int8_t bx,by;
    for (i=0;i<4;i++) {
        c=shapes[stack_piece][stack_rotation][i]; bx=stack_x+(c&3); by=stack_y+(c>>2);
        if (by<0) { finish_game(0); return; }
        stack_board[(uint8_t)by*10+bx]=stack_piece+1;
    }
    row=13;
    while (row>=0) {
        full=1;
        for (x=0;x<10;x++) if (!stack_board[(uint8_t)row*10+x]) full=0;
        if (full) {
            for (y=(uint8_t)row;y>0;y--) memcpy(stack_board+y*10,stack_board+(y-1)*10,10);
            memset(stack_board,0,10); cleared++;
        } else row--;
    }
    if (cleared) { stack_lines+=cleared; score+=(uint16_t)cleared*cleared*100; tone(230); }
    else tone(100);
    spawn();
}
static void rotate(int8_t direction) {
    uint8_t r=(stack_rotation+direction)&3, i;
    static const int8_t kick[]={0,-1,1,-2,2};
    for (i=0;i<5;i++) if (fits(stack_x+kick[i],stack_y,r)) {
        stack_x+=kick[i]; stack_rotation=r; redraw=1; tone(150); return;
    }
    if (fits(stack_x,stack_y-1,r)) { stack_y--; stack_rotation=r; redraw=1; }
}
void stack_tick(void) {
    uint8_t move_keys=pressed;
    if (!(frame_count%6)) move_keys|=keys&(J_LEFT|J_RIGHT);
    if ((move_keys&J_LEFT) && fits(stack_x-1,stack_y,stack_rotation)) { stack_x--; redraw=1; }
    if ((move_keys&J_RIGHT) && fits(stack_x+1,stack_y,stack_rotation)) { stack_x++; redraw=1; }
    if (pressed&J_A) rotate(1);
    if (pressed&J_B) rotate(-1);
    if (pressed&J_UP) {
        while (fits(stack_x,stack_y+1,stack_rotation)) { stack_y++; score+=2; }
        lock_piece(); return;
    }
    drop_clock++;
    if (((keys&J_DOWN) && !(frame_count%2)) || drop_clock>=30-(stack_lines>20 ? 20 : stack_lines)) {
        drop_clock=0;
        if (fits(stack_x,stack_y+1,stack_rotation)) { stack_y++; redraw=1; if (keys&J_DOWN) score++; }
        else lock_piece();
    }
}
void stack_draw(void) {
    uint8_t x,y,i,c; int8_t gy=stack_y,bx,by;
    text(0,0,"STACK SHIFT");
    for (y=0;y<14;y++) {
        tile(0,y+2,TILE_GHOST); tile(11,y+2,TILE_GHOST);
        for (x=0;x<10;x++) if (stack_board[y*10+x]) tile(x+1,y+2,127+stack_board[y*10+x]);
    }
    for (x=0;x<12;x++) tile(x,16,TILE_GHOST);
    while (fits(stack_x,gy+1,stack_rotation)) gy++;
    for (i=0;i<4;i++) {
        c=shapes[stack_piece][stack_rotation][i]; x=c&3; y=c>>2;
        bx=stack_x+x+1; by=gy+y+2;
        if (by>=2 && by<16) tile(bx,by,TILE_GHOST);
        by=stack_y+y+2;
        if (by>=2 && by<16) tile(bx,by,TILE_BLOCK+stack_piece);
    }
    text(13,3,"SCORE"); number(13,4,score,5);
    text(13,6,"LINES"); number(14,7,stack_lines,3);
    text(13,9,"NEXT");
    for (i=0;i<4;i++) { c=shapes[stack_next][0][i]; tile(13+(c&3),10+(c>>2),TILE_BLOCK+stack_next); }
    text(12,14,"UP DROP"); text(12,15,"A/B TURN");
}
