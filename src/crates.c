#include "arcade.h"

uint8_t crates_board[64], crates_x, crates_y, crates_level, crates_on_goals;
uint16_t crates_moves;
static uint8_t undo_board[64], undo_x, undo_y, can_undo, next_clock;
/* # wall, . target, $ box, @ player. Layouts are authored and solvable. */
static const char levels[3][65]={
    "########"
    "#      #"
    "# . .  #"
    "# $ $  #"
    "#  @   #"
    "#      #"
    "#      #"
    "########",
    "########"
    "#      #"
    "# .#.  #"
    "# $ $  #"
    "#   @  #"
    "# $ .  #"
    "#      #"
    "########",
    "########"
    "#      #"
    "# . .  #"
    "# $$   #"
    "#   @# #"
    "# $ .  #"
    "#      #"
    "########"
};

static void load_level(void) {
    uint8_t i; char c;
    for (i=0;i<64;i++) {
        c=levels[crates_level][i];
        crates_board[i]= c=='#' ? 1 : c=='.' ? 2 : c=='$' ? 4 : 0;
        if (c=='@') { crates_x=i&7; crates_y=i>>3; }
    }
    crates_on_goals=0; crates_moves=0; can_undo=0; next_clock=0; redraw=1;
}
void crates_init(void) { crates_level=0; load_level(); }
static void recount(void) {
    uint8_t i,boxes=0; crates_on_goals=0;
    for (i=0;i<64;i++) if (crates_board[i]&4) { boxes++; if (crates_board[i]&2) crates_on_goals++; }
    if (boxes==crates_on_goals) { score+=300; next_clock=40; tone(230); }
}
void crates_tick(void) {
    int8_t dx=0,dy=0,nx,ny,bx,by; uint8_t i,j,repeat=pressed;
    if (next_clock) {
        if (!--next_clock) {
            if (crates_level==2) finish_game(1); else { crates_level++; load_level(); }
        }
        return;
    }
    if (pressed&J_A) { load_level(); return; }
    if ((pressed&J_B) && can_undo) {
        memcpy(crates_board,undo_board,64); crates_x=undo_x; crates_y=undo_y;
        if (crates_moves) crates_moves--; can_undo=0; redraw=1; recount(); return;
    }
    if (!(frame_count%9)) repeat|=keys&(J_LEFT|J_RIGHT|J_UP|J_DOWN);
    if (repeat&J_LEFT) dx=-1; else if (repeat&J_RIGHT) dx=1;
    else if (repeat&J_UP) dy=-1; else if (repeat&J_DOWN) dy=1;
    else return;
    nx=crates_x+dx; ny=crates_y+dy;
    if (nx<0 || nx>7 || ny<0 || ny>7) return;
    i=ny*8+nx; if (crates_board[i]&1) return;
    j=i;
    if (crates_board[i]&4) {
        bx=nx+dx; by=ny+dy;
        if (bx<0 || bx>7 || by<0 || by>7) return;
        j=by*8+bx; if (crates_board[j]&5) return;
    }
    memcpy(undo_board,crates_board,64); undo_x=crates_x; undo_y=crates_y; can_undo=1;
    if (crates_board[i]&4) { crates_board[i]&=~4; crates_board[j]|=4; tone(150); }
    crates_x=nx; crates_y=ny; crates_moves++; redraw=1; recount();
}
void crates_draw(void) {
    uint8_t x,y,c,t;
    text(0,0,"CRATEWORKS"); text(13,0,"ROOM"); number(18,0,crates_level+1,1);
    text(0,2,"MOVES"); number(6,2,crates_moves,4);
    for (y=0;y<8;y++) for (x=0;x<8;x++) {
        c=crates_board[y*8+x];
        t=(c&1) ? TILE_WALL : (c&4) ? ((c&2) ? TILE_CRATE_OK : TILE_CRATE) : (c&2) ? TILE_TARGET : TILE_FLOOR;
        tile(6+x,5+y,t);
    }
    tile(6+crates_x,5+crates_y,TILE_HERO);
    text(0,14,next_clock ? "ROOM COMPLETE!" : "B UNDO  A RESET");
    text(0,15,"PUSH BOXES ON TARGETS");
}
