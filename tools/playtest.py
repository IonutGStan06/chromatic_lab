"""Input-driven tests on the compiled ROM, with genuine framebuffer evidence.

Reads linker-named game state to assert behavior; never writes emulator memory.
Run from the repository root: make test
"""
import hashlib
import json
import re
import sys
from collections import deque
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageDraw
from pyboy import PyBoy

ROM = Path(sys.argv[1] if len(sys.argv)>1 else 'build/chromatic-arcade.gbc').resolve()
OUT = ROM.parent / 'playtest'
OUT.mkdir(exist_ok=True)
SYMBOLS = {name:int(value,16) for name,value in re.findall(
    r'DEF (_\w+) (0x[0-9A-Fa-f]+)', ROM.with_suffix('.noi').read_text())}
BUTTONS = {'right':1,'left':2,'up':4,'down':8,'a':16,'b':32,'select':64,'start':128}
RESULTS=[]


class Session:
    def __init__(self,cgb=True):
        # PyBoy selects its boot ROM from the cartridge flag even with cgb=False.
        # Select the bundled DMG boot ROM explicitly to test genuine DMG startup.
        bootrom=None if cgb else str(files('pyboy.core').joinpath('bootrom_dmg.bin'))
        self.p=PyBoy(str(ROM),window='null',sound_emulated=False,cgb=cgb,bootrom=bootrom)
        self.p.set_emulation_speed(0)
        self.held=set()
        self.p.tick(180,True)
        self.wait(lambda:self.u16('frame_count')>0 and self.p.memory[0xFF40]&0x80,
                  'ROM did not finish initializing the display')
        assert self.u8('game_mode')==0, 'ROM did not reach launcher'
        assert self.p.memory[SYMBOLS['__cpu']]==(0x11 if cgb else 1), 'Wrong boot hardware identity'

    def close(self): self.p.stop(save=False)
    def u8(self,name): return self.p.memory[SYMBOLS['_'+name]]
    def u16(self,name):
        addr=SYMBOLS['_'+name]
        return self.p.memory[addr] | self.p.memory[addr+1]<<8
    def s16(self,name):
        n=self.u16(name); return n-65536 if n>32767 else n
    def s8(self,name):
        n=self.u8(name); return n-256 if n>127 else n
    def data(self,name,count):
        addr=SYMBOLS['_'+name]; return tuple(self.p.memory[addr:addr+count])
    def wait(self,predicate,message,limit=600):
        for _ in range(limit):
            if predicate(): return
            self.p.tick(1,True)
        raise AssertionError(message)
    def buttons(self,buttons):
        new=set(buttons)
        for button in self.held-new: self.p.button_release(button)
        for button in new-self.held: self.p.button_press(button)
        self.held=new
        mask=sum(BUTTONS[b] for b in new)
        self.wait(lambda:self.u8('keys')==mask, f'Input {new} not observed')
    def tap(self,button):
        self.buttons([button]); self.buttons([])
    def frames(self,count):
        start=self.u16('frame_count')
        self.wait(lambda:((self.u16('frame_count')-start)&65535)>=count,
                  f'Game clock stopped in mode {self.u8("game_mode")}', max(600,count*30))
    def enter(self,choice):
        if self.u8('game_mode'): self.tap('select')
        while self.u8('menu_choice')!=choice: self.tap('down')
        self.tap('a')
        assert self.u8('game_mode')==choice+1, 'Incorrect game selected'
    def capture(self,name):
        self.wait(lambda:not self.u8('redraw'),'Frame did not finish')
        self.p.tick(2,True)
        picture=self.p.screen.image.copy()
        picture.save(OUT / f'{name}.png')
        assert picture.size==(160,144)
        assert len(picture.getcolors(23040))>1, 'Blank framebuffer'
    def pause_check(self,names):
        self.tap('start'); assert self.u8('paused')==1
        state=[self.u16(n) for n in names]; clock=self.u16('frame_count')
        self.p.tick(60,True)
        assert state==[self.u16(n) for n in names], 'Game moved while paused'
        assert clock==self.u16('frame_count'), 'Clock advanced while paused'
        self.tap('start'); assert self.u8('paused')==0


def check(name,fn):
    fn(); RESULTS.append({'check':name,'outcome':'passed'})
    print(f'PASS {name}',flush=True)


def cartridge():
    data=ROM.read_bytes()
    assert len(data)==32768 and data[0x143]==0x80
    assert data[0x147:0x14a]==bytes([0,0,0]), 'Expected ROM-only cartridge, no SRAM'
    value=0
    for byte in data[0x134:0x14d]: value=(value-byte-1)&255
    assert value==data[0x14d], 'Header checksum failed'
    assert (sum(data)-data[0x14e]-data[0x14f])&65535==int.from_bytes(data[0x14e:0x150],'big'), 'Global checksum failed'


def launcher():
    for cgb in (True,False):
        s=Session(cgb)
        try:
            s.capture('launcher-color' if cgb else 'launcher-mono')
            for game in range(5):
                s.enter(game); assert not s.u8('game_over')
                s.capture(f'{game+1}-boot-'+('color' if cgb else 'mono'))
                s.pause_check(['score'])
                s.tap('select'); assert s.u8('game_mode')==0
        finally: s.close()


def sprite_overlays():
    def positions(s):
        # Read real hardware OAM after completed frames; never move a sprite
        # through emulator memory. Each entry begins with screen Y and X.
        return [(s.p.memory[0xFE00+i],s.p.memory[0xFE01+i])
                for i in range(0,160,4)]

    for choice,name in ((1,'ember-run'),(3,'orbit-drift')):
        s=Session()
        try:
            s.enter(choice); s.frames(12)
            assert any(y and x for y,x in positions(s)), 'Gameplay sprites absent before pause'
            s.tap('start'); assert s.u8('paused')
            s.capture(name+'-paused')
            assert all(y==0 and x==0 for y,x in positions(s)), 'Sprites can obscure the pause overlay'
            s.tap('start'); assert not s.u8('paused')
            s.capture(name+'-resumed')
            assert any(y and x for y,x in positions(s)), 'Resume did not restore gameplay sprites'
            if choice==1:
                s.buttons(['right'])
                s.wait(lambda:s.u8('game_over')==1,'Runner did not fall into a gap',3000)
                s.buttons([]); s.capture(name+'-game-over')
                assert all(y==0 and x==0 for y,x in positions(s)), 'Sprites can obscure the game-over overlay'
                s.tap('a'); assert not s.u8('game_over')
                s.capture(name+'-retried')
                assert any(y and x for y,x in positions(s)), 'Retry did not restore gameplay sprites'
        finally: s.close()


# Sparse tetromino coordinates provide legal placements to an input-only player.
SHAPES=[
    [[4,5,6,7],[2,6,10,14],[4,5,6,7],[2,6,10,14]],
    [[1,2,5,6]]*4,
    [[4,5,6,9],[1,4,5,9],[1,4,5,6],[1,5,6,9]],
    [[0,4,5,6],[1,2,5,9],[4,5,6,10],[1,5,8,9]],
    [[2,4,5,6],[1,5,9,10],[4,5,6,8],[0,1,5,9]],
    [[1,2,4,5],[1,5,6,10],[1,2,4,5],[1,5,6,10]],
    [[0,1,5,6],[2,5,6,9],[0,1,5,6],[2,5,6,9]],
]


def best_drop(board,piece):
    options=[]
    for rotation,packed in enumerate(SHAPES[piece]):
        cells=[(c&3,c>>2) for c in packed]
        def fits(x,y):
            return all(0<=x+cx<10 and y+cy<14 and
                       (y+cy<0 or not board[(y+cy)*10+x+cx]) for cx,cy in cells)
        for x in range(-3,10):
            if not fits(x,-1): continue
            y=-1
            while fits(x,y+1): y+=1
            if any(y+cy<0 for cx,cy in cells): continue
            rows=[list(board[i*10:(i+1)*10]) for i in range(14)]
            for cx,cy in cells: rows[y+cy][x+cx]=piece+1
            cleared=sum(all(row) for row in rows)
            rows=[row for row in rows if not all(row)]
            rows=[[0]*10 for _ in range(14-len(rows))]+rows
            heights=[]; holes=0
            for col in range(10):
                occupied=[i for i in range(14) if rows[i][col]]
                height=14-occupied[0] if occupied else 0
                heights.append(height)
                if height: holes+=sum(not rows[i][col] for i in range(occupied[0],14))
            value=cleared*12-sum(heights)*0.6-holes*7-sum(abs(a-b) for a,b in zip(heights,heights[1:]))*0.4
            options.append((value,rotation,x))
    assert options,'No legal stack placement'
    return max(options)[1:]


def stacking():
    s=Session()
    try:
        s.enter(0)
        s.pause_check(['score'])
        for placed in range(32):
            assert not s.u8('game_over'), 'Stack player topped out'
            rotation,x=best_drop(s.data('stack_board',140),s.u8('stack_piece'))
            for _ in range(rotation): s.tap('a')
            assert s.u8('stack_rotation')==rotation
            for _ in range(15):
                current=s.s8('stack_x')
                if current==x: break
                s.tap('left' if current>x else 'right')
            assert s.s8('stack_x')==x, 'Piece failed to move into place'
            s.tap('up')
            if placed==10: s.capture('stack-shift')
        assert s.u8('stack_lines')>=4, 'Hard drops did not clear rows'
        assert s.u16('score')>=400, 'Score did not reflect cleared rows'
        # Fill the middle until a real input-driven top-out, then retry.
        for _ in range(30):
            if s.u8('game_over'): break
            s.tap('up')
        assert s.u8('game_over')==1, 'Top-out did not end the game'
        s.tap('a'); assert not s.u8('game_over') and not s.u8('stack_lines')
    finally: s.close()


def platformer():
    s=Session()
    try:
        s.enter(1); s.frames(12)
        assert s.u8('runner_grounded')
        start=s.s16('runner_x'); s.buttons(['right']); s.frames(12); s.buttons([])
        assert s.s16('runner_x')>start, 'Runner did not move'
        before=s.s16('runner_y'); s.buttons(['a']); s.frames(5)
        assert s.s16('runner_y')<before, 'Jump did not leave the ground'
        s.buttons([]); s.frames(35); assert s.u8('runner_grounded')
        s.capture('ember-run')
        s.pause_check(['runner_x','runner_y'])
        # Deliberately walk into the first gap and verify death/retry.
        s.buttons(['right'])
        s.wait(lambda:s.u8('game_over')==1,'Falling into gap did not end game',3000)
        s.buttons([]); s.tap('a')
        assert not s.u8('game_over') and s.s16('runner_x')==24*16
    finally: s.close()


def dungeon():
    s=Session()
    try:
        s.enter(2)
        s.tap('a')
        assert s.u8('vault_shots')>=1 and s.u8('vault_kills')==1, 'Visible sentinel was not hit'
        assert s.u16('score')==100
        s.tap('b'); assert s.u8('vault_map')==1
        s.tap('b'); assert s.u8('vault_map')==0
        angle=s.u8('vault_angle'); s.tap('right'); s.buttons(['right']); s.frames(8); s.buttons([])
        assert s.u8('vault_angle')!=angle, 'Turn did not rotate view'
        s.capture('iron-vault')
        s.pause_check(['score'])
        # Survive a stationary encounter until enemies cause an actual loss.
        s.wait(lambda:s.u8('game_over')==1,'Sentinels did not damage the player',15000)
        assert s.u8('vault_health')==0
        s.tap('a'); assert s.u8('vault_health')==5 and not s.u8('game_over')
    finally: s.close()


def asteroids():
    s=Session()
    try:
        s.enter(3)
        s.buttons(['up']); s.frames(18); s.buttons([])
        assert s.s16('orbit_vy')<0, 'Thrust did not accelerate ship'
        start=s.s16('orbit_y'); s.frames(4)
        assert s.s16('orbit_y')!=start, 'Ship inertia stopped on release'
        s.tap('right'); s.buttons(['a'])
        s.wait(lambda:any(s.data('orbit_bullet_alive',4)), 'Shot not emitted')
        s.buttons([]); s.capture('orbit-drift')
        s.pause_check(['orbit_x','orbit_y'])
        # Shoot while rotating and drifting; must produce a real rock hit.
        s.buttons(['a','right','up'])
        s.wait(lambda:s.u16('score')>=50,'Shots never destroyed a rock',6000)
        s.buttons([])
    finally: s.close()


def solve_crates(board,player):
    walls={i for i,c in enumerate(board) if c&1}
    goals=frozenset(i for i,c in enumerate(board) if c&2)
    boxes=frozenset(i for i,c in enumerate(board) if c&4)
    queue=deque([(player,boxes,'')]); visited={(player,boxes)}
    moves=[(-1,'left'),(1,'right'),(-8,'up'),(8,'down')]
    while queue:
        pos,boxes,path=queue.popleft()
        if boxes==goals: return path.split(',') if path else []
        for delta,button in moves:
            new=pos+delta
            if not 0<=new<64 or new in walls: continue
            next_boxes=boxes
            if new in boxes:
                dest=new+delta
                if not 0<=dest<64 or dest in walls or dest in boxes: continue
                # A box trapped in a non-goal corner cannot be solved.
                if dest not in goals and (dest-1 in walls or dest+1 in walls) and (dest-8 in walls or dest+8 in walls): continue
                next_boxes=frozenset((boxes-{new})|{dest})
            state=(new,next_boxes)
            if state not in visited:
                visited.add(state); queue.append((new,next_boxes,path+(',' if path else '')+button))
        assert len(visited)<500000, 'Crate search exceeded expected puzzle complexity'
    raise AssertionError('Authored crate room is unsolvable')


def sokoban():
    s=Session()
    try:
        s.enter(4)
        original=s.data('crates_board',64); x,y=s.u8('crates_x'),s.u8('crates_y')
        s.tap('left'); assert s.u16('crates_moves')==1
        s.tap('b')
        assert s.data('crates_board',64)==original and (s.u8('crates_x'),s.u8('crates_y'))==(x,y)
        assert s.u16('crates_moves')==0
        for level in range(3):
            assert s.u8('crates_level')==level
            board=s.data('crates_board',64); pos=s.u8('crates_y')*8+s.u8('crates_x')
            solution=solve_crates(board,pos)
            for button in solution: s.tap(button)
            if level==0: s.capture('crateworks')
            if level<2:
                s.wait(lambda:s.u8('crates_level')==level+1,'Solved room did not advance')
                # The level byte changes before the 64-cell initialization ends.
                # Wait for complete game loops before reading the next board.
                s.frames(2)
            else:
                s.wait(lambda:s.u8('game_over')==2,'Final room did not win')
        assert s.u16('score')==900
        s.tap('a'); assert s.u8('crates_level')==0 and not s.u8('game_over')
    finally: s.close()


def contact_sheet():
    names=['launcher-color','stack-shift','ember-run','iron-vault','orbit-drift','crateworks']
    sheet=Image.new('RGB',(960,620),(15,20,31)); draw=ImageDraw.Draw(sheet)
    for i,name in enumerate(names):
        x=(i%3)*320; y=(i//3)*310
        draw.text((x+8,y+5),name.upper(),fill=(245,238,208))
        sheet.paste(Image.open(OUT/f'{name}.png').convert('RGB').resize((320,288),Image.Resampling.NEAREST),(x,y+22))
    sheet.save(ROM.parent/'arcade-preview.png')


try:
    check('32 KB color-compatible cartridge and checksums',cartridge)
    check('all five games boot, pause and return in CGB and DMG modes',launcher)
    check('pause and game-over overlays hide sprites, resume and retry restore them',sprite_overlays)
    check('stack movement, rotation, hard drop, line clearing, top-out and retry',stacking)
    check('platform movement, jump, landing, gap death, pause and retry',platformer)
    check('raycast shooter rotation, hit, score, damage, pause and retry',dungeon)
    check('asteroid thrust, inertia, firing, rock hit and pause',asteroids)
    check('crate undo and three puzzle completions through controller input',sokoban)
    contact_sheet()
except Exception as exc:
    RESULTS.append({'check':'current run','outcome':'failed','error':str(exc)})
    raise
finally:
    (OUT/'results.json').write_text(json.dumps({
        'rom':ROM.name,'size_bytes':ROM.stat().st_size,
        'sha256':hashlib.sha256(ROM.read_bytes()).hexdigest(),
        'checks':RESULTS,'hardware_tested':False},indent=2)+'\n')
