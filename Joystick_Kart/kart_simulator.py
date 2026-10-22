"""Raspberry Pi 5 joystick dashboard. apt install python3-serial python3-tk"""
import argparse
import math
import queue
import threading
import time
import tkinter as tk

import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser()
parser.add_argument('--port', help='Example: /dev/ttyACM0')
parser.add_argument('--swap-axes', action='store_true')
parser.add_argument('--invert-x', action='store_true')
parser.add_argument('--invert-y', action='store_true')
parser.add_argument('--windowed', action='store_true')
args = parser.parse_args()
messages = queue.Queue(maxsize=1)
stop = threading.Event()


def receive():
    while not stop.is_set():
        ports = [args.port] if args.port else [
            p.device for p in list_ports.comports()
            if 'ttyACM' in p.device or 'ttyUSB' in p.device]
        for port in ports:
            try:
                with serial.Serial(port, 115200, timeout=0.2) as connection:
                    while not stop.is_set():
                        line = connection.readline().decode('ascii', errors='ignore').strip()
                        try:
                            x, y, button = map(int, line.split(','))
                            if not (0 <= x <= 1023 and 0 <= y <= 1023 and button in (0, 1)):
                                continue
                        except ValueError:
                            continue
                        sample = (x, y, button, time.monotonic(), port)
                        try:
                            messages.get_nowait()
                        except queue.Empty:
                            pass
                        messages.put_nowait(sample)
            except (serial.SerialException, OSError):
                pass
        stop.wait(0.5)



import random
root = tk.Tk()
root.title('Joystick Kart')
root.geometry('1024x600')
root.attributes('-fullscreen', not args.windowed)
canvas = tk.Canvas(root, bg='#70cfff', highlightthickness=0)
canvas.pack(fill='both', expand=True)
random.seed(12)
objects = [(i * 95 + 180, random.choice([-0.65, 0, 0.65]),
            'cone' if i % 3 == 0 else 'coin') for i in range(42)]
TRACK = 4200.0
HIT_Z = 65.0
HIT_DEPTH = 14.0
coin_popups = []
speed = rpm = distance = player = 0.0
coins = hits = 0
sample = None
center_x = center_y = 512
calibrated = False
input_status = "CENTER: 512 / 512"
previous = time.monotonic()
last_button = 1
boost_until = collision_until = 0.0
boost_ready = 0.0
GAME_DURATION = 20.0
race_started = None
hit_flash_started = None
collected = set()
keys = set()

def reset(event=None):
    global race_started, hit_flash_started
    race_started = None
    hit_flash_started = None
    global speed, rpm, distance, player, coins, hits, boost_until, collision_until, boost_ready
    speed = rpm = distance = player = 0.0
    coins = hits = 0
    boost_until = collision_until = boost_ready = 0.0
    collected.clear()
    coin_popups.clear()

def close(event=None):
    stop.set()
    root.destroy()

def calibrate(event=None):
    global center_x, center_y, calibrated, input_status
    if sample and time.monotonic() - sample[3] < 0.5:
        x, y = sample[:2]
        # Do not mistake a held direction for the neutral position.
        if 350 <= x <= 674 and 350 <= y <= 674:
            center_x, center_y = x, y
            calibrated = True
            input_status = f'CENTER: {x} / {y}'
        else:
            input_status = 'RELEASE STICK, THEN CALIBRATE'

BUTTONS = [(610, 720, 'RESET', reset),
           (730, 880, 'CALIBRATE', calibrate),
           (890, 1004, 'EXIT', close)]

def axis(value, center):
    delta = value - center
    if abs(delta) < 60:
        return 0.0
    span = 1023-center if delta > 0 else center
    return math.copysign(min(1, (abs(delta)-60)/max(1, span-60)), delta)

def joystick_controls(raw_x, raw_y):
    # User's mounting: forward raises VRx; right raises VRy.
    steer = axis(raw_y, center_y)
    throttle = axis(raw_x, center_x)
    if args.swap_axes:
        steer, throttle = throttle, steer
    if args.invert_x:
        steer = -steer
    if args.invert_y:
        throttle = -throttle
    return steer, throttle

def race_pace(elapsed):
    # Normal limit, boosted limit, acceleration per second.
    stage = min(3, max(0, int(elapsed // 5)))
    speed_limit = (160, 220, 300, 360)[stage]
    return speed_limit, speed_limit + 50, 65 + stage * 20

def bend(pos):
    return math.sin(pos*2*math.pi/TRACK)*0.8 + math.sin(pos*6*math.pi/TRACK)*0.25

def project_at(z, travel, lateral):
    t = max(0, min(1, 1-z/950))
    y = 195 + t*t*405
    width = 28 + t*t*410
    curve = (bend(travel+z)-bend(travel))*t*180
    return 512+curve-lateral*width, y, width

def project(z):
    return project_at(z, distance, player)

def swept_hit(marker, lane, kind, old_distance, new_distance, old_player, new_player):
    """Sweep the visible object past the kart, including lateral movement."""
    advance = new_distance-old_distance
    if advance <= 0:
        return False
    enter = max(0.0, (marker-(HIT_Z+HIT_DEPTH)-old_distance)/advance)
    leave = min(1.0, (marker-(HIT_Z-HIT_DEPTH)-old_distance)/advance)
    if enter > leave:
        return False
    gaps = []
    radii = []
    for fraction in (enter, leave):
        travel = old_distance + advance*fraction
        lateral = old_player+(new_player-old_player)*fraction
        cx, _, width = project_at(marker-travel, travel, lateral)
        gaps.append(cx+lane*width-512)
        radii.append(64+width*(0.045 if kind == 'coin' else 0.075))
    # Sweeping prevents skipping collisions at high speed or while steering.
    return (abs(gaps[0]) <= radii[0] or abs(gaps[1]) <= radii[1]
            or gaps[0]*gaps[1] <= 0)

def frame():
    global race_started, hit_flash_started
    global sample, calibrated, center_x, center_y, previous, speed, rpm, distance, player
    global coins, hits, last_button, boost_until, collision_until, boost_ready
    now = time.monotonic()
    dt = min(0.05, now-previous)
    previous = now
    try:
        sample = messages.get_nowait()
    except queue.Empty:
        pass
    connected = sample is not None and now-sample[3] < 0.5
    steer = throttle = 0.0
    button = 1
    if connected:
        # Retain neutral defaults or explicit calibration across reconnects.
        steer, throttle = joystick_controls(sample[0], sample[1])
        button = sample[2]
    keyboard = bool(keys & {'Left','Right','Up','Down','space'})
    if keyboard:
        steer = float('Right' in keys)-float('Left' in keys)
        throttle = float('Up' in keys)-float('Down' in keys)
        button = 0 if 'space' in keys else 1
    active = connected or keyboard
    # Start the timer on the first acceleration input; keep counting if USB disconnects.
    if race_started is None and active and throttle > 0.1:
        race_started = now
    remaining = GAME_DURATION if race_started is None else max(0.0, GAME_DURATION-(now-race_started))
    finished = remaining <= 0
    if button == 0 and last_button == 1 and now >= boost_ready and active and not finished:
        boost_until = now+1.8
        boost_ready = now+6
    last_button = button
    boosted = now < boost_until and not finished
    elapsed = 0.0 if race_started is None else max(0.0, now-race_started)
    late_race = elapsed >= 5.0
    if active and not finished:
        speed_limit, boost_limit, acceleration_rate = race_pace(elapsed)
        acceleration = throttle*acceleration_rate if throttle > 0 else throttle*110-12
        speed = max(0, min(boost_limit if boosted else speed_limit,
                           speed+(acceleration+(100 if boosted else 0))*dt))
        old_player = player
        player += steer*dt*(0.6+speed/100)-bend(distance)*speed*dt*0.0018
        player = max(-1.5, min(1.5, player))
        if abs(player) > 1:
            speed = max(0, speed-70*dt)
        old = distance
        distance += speed*dt*1.15
        for lap in range(max(0, int(old//TRACK)), int((distance+HIT_Z+HIT_DEPTH)//TRACK)+1):
            for index, (pos, lane, kind) in enumerate(objects):
                marker = lap*TRACK+pos
                key = (lap,index)
                if key in collected:
                    continue
                if swept_hit(marker, lane, kind, old, distance, old_player, player):
                    collected.add(key)
                    if kind == 'coin':
                        coins += 1
                        coin_popups.append(now)
                    else:
                        speed *= 0.45
                        hits += 1
                        collision_until = now+0.5
                        hit_flash_started = now
                elif marker-distance < HIT_Z-HIT_DEPTH:
                    collected.add(key)
        # Bound memory to nearby laps.
        current_lap = int(distance//TRACK)
        collected.difference_update({key for key in collected if key[0] < current_lap-1})
    else:
        speed = max(0, speed-100*dt)
    if finished:
        speed = rpm = 0.0
    target_rpm = 0.0 if finished else 800+speed*30+(1000 if boosted else 0)
    rpm += (target_rpm-rpm)*(1-math.exp(-dt/0.15))
    canvas.delete('all')
    sx, sy = max(1,canvas.winfo_width())/1024, max(1,canvas.winfo_height())/600
    scale = min(sx,sy)
    def rect(x1,y1,x2,y2,fill,outline=''):
        return canvas.create_rectangle(x1*sx,y1*sy,x2*sx,y2*sy,fill=fill,outline=outline)
    def oval(x1,y1,x2,y2,fill,outline=''):
        return canvas.create_oval(x1*sx,y1*sy,x2*sx,y2*sy,fill=fill,outline=outline)
    def poly(coords,fill):
        return canvas.create_polygon(*[v*(sx if i%2==0 else sy) for i,v in enumerate(coords)],fill=fill)
    def text(x,y,value,size=18,color='white',anchor='center'):
        return canvas.create_text(x*sx,y*sy,text=value,fill=color,anchor=anchor,
          font=('DejaVu Sans', max(8,int(size*scale)), 'bold'))
    rect(0,0,1024,600,'#78d4fc')
    oval(830,30,920,120,'#fff4ae')
    for x in [90,380,650]:
        oval(x,65,x+130,100,'#eafbff')
    poly([0,200,120,110,250,200,440,120,650,200,840,100,1024,200],'#51ad75')
    rect(0,195,1024,600,'#55bd59')
    # Draw distant road sections first, then near sections.
    for z in range(950,0,-12):
        c1,y1,w1 = project(z)
        c2,y2,w2 = project(max(0,z-12))
        stripe = int((distance+z)/45)%2
        poly([c1-w1*1.12,y1,c1+w1*1.12,y1,c2+w2*1.12,y2,c2-w2*1.12,y2],
             '#f6f1dd' if stripe else '#ed5462')
        poly([c1-w1,y1,c1+w1,y1,c2+w2,y2,c2-w2,y2], '#4b5265' if stripe else '#454c60')
        if stripe:
            for lane in [-0.33,0.33]:
                poly([c1+w1*(lane-.012),y1,c1+w1*(lane+.012),y1,
                      c2+w2*(lane+.012),y2,c2+w2*(lane-.012),y2],'#e9e5b8')
    visible=[]
    for lap in [int(distance//TRACK),int(distance//TRACK)+1]:
        for index,(pos,lane,kind) in enumerate(objects):
            z=lap*TRACK+pos-distance
            if 0<z<950 and (lap,index) not in collected:
                visible.append((z,lane,kind))
    for z,lane,kind in sorted(visible,reverse=True):
        cx,y,width=project(z)
        x=cx+lane*width
        size=max(3,width*0.075)
        oval(x-size,y-size*.15,x+size,y+size*.2,'#334c49')
        if kind=='coin':
            oval(x-size*.6,y-size*2,x+size*.6,y,'#ffd24a','#fff3a0')
            text(x,y-size,'$',max(8,int(size)),'#9c6500')
        else:
            poly([x,y-size*2.3,x-size,y,x+size,y],'#ff833f')
            rect(x-size*.5,y-size,x+size*.5,y-size*.65,'#fff0c8')
    # Rear-view Mario kart, layered vector art for crisp small-screen rendering.
    kx = 512
    body = '#ee3346' if now > collision_until else '#ffd166'
    # Ground shadow and boost flames.
    oval(kx-81, 535, kx+81, 565, '#314840')
    if boosted:
        for exhaust_x in (kx-36, kx+36):
            flame = 8*math.sin(now*35)
            poly([exhaust_x-12,543,exhaust_x,590+flame,exhaust_x+12,543], '#ff823c')
            poly([exhaust_x-6,543,exhaust_x,572+flame,exhaust_x+6,543], '#fff0a0')
    # Axle and treaded wheels.
    rect(kx-65,507,kx+65,525,'#243044')
    for dx in (-78, 51):
        rect(kx+dx,487,kx+dx+27,548,'#111827')
        rect(kx+dx+4,491,kx+dx+23,544,'#283244')
        for yy in range(497,541,10):
            rect(kx+dx+3,yy,kx+dx+24,yy+3,'#465064')
        rect(kx+dx+10,503,kx+dx+18,531,'#7d8c9d')
    # Red chassis, side pods and seat.
    poly([kx-46,465,kx+46,465,kx+64,538,kx+49,552,
          kx-49,552,kx-64,538],body)
    poly([kx-46,474,kx-62,523,kx-45,532,kx-30,480],'#ad1834')
    poly([kx+46,474,kx+62,523,kx+45,532,kx+30,480],'#ff6871')
    oval(kx-38,452,kx+38,507,'#26334d')
    # Arms and white gloves on the wheel, seen from behind.
    poly([kx-23,445,kx-42,451,kx-48,480,kx-34,485,kx-19,459],'#ce2338')
    poly([kx+23,445,kx+42,451,kx+48,480,kx+34,485,kx+19,459],'#f54b4b')
    oval(kx-47,466,kx-28,484,'#fff9ee','#bdc9d9')
    oval(kx+28,466,kx+47,484,'#fff9ee','#bdc9d9')
    # Red shirt and blue overalls.
    oval(kx-27,434,kx+27,488,'#e92c40')
    poly([kx-24,455,kx+24,455,kx+29,488,kx+20,500,
          kx-20,500,kx-29,488],'#245fc6')
    rect(kx-22,444,kx-13,477,'#4488e7')
    rect(kx+13,444,kx+22,477,'#4488e7')
    rect(kx-12,474,kx+12,490,'#367add')
    # Neck, ears, brown hair and distinctive red cap.
    rect(kx-12,422,kx+12,443,'#e7a16b')
    oval(kx-34,403,kx-19,425,'#f8bc88','#d89160')
    oval(kx+19,403,kx+34,425,'#f8bc88','#d89160')
    oval(kx-27,389,kx+27,437,'#6c3421')
    for dx in (-23,-12,0,12):
        oval(kx+dx,417,kx+dx+12,437,'#6c3421')
    oval(kx-33,370,kx+33,417,'#d51d32')
    oval(kx-29,373,kx+29,405,'#f43744')
    oval(kx-22,376,kx+18,390,'#ff6065')
    poly([kx-33,401,kx+33,401,kx+30,413,kx-30,413],'#ac172c')
    rect(kx-12,404,kx+12,411,'#ee3849')
    oval(kx-2,405,kx+2,409,'#fff1d1')
    # Exposed rear engine, metal fins, exhausts and bumper.
    rect(kx-25,499,kx+25,533,'#303c50')
    rect(kx-20,502,kx+20,526,'#8e9aa8')
    for yy in (505,511,517,523):
        rect(kx-19,yy,kx+19,yy+2,'#d3dce3')
    for dx in (-44,29):
        rect(kx+dx,514,kx+dx+15,543,'#8693a4')
        oval(kx+dx,535,kx+dx+15,548,'#dce4ec')
        oval(kx+dx+3,538,kx+dx+12,545,'#182132')
    rect(kx-59,542,kx+59,552,'#dce4ec')
    rect(kx-53,552,kx+53,556,'#748297')
    rect(kx-22,534,kx+22,548,body)
    oval(kx-9,534,kx+9,548,'#fff5e8')
    text(kx,541,'M',10,'#db253d')
    # Floating pickup feedback above the character; outlined for small LCDs.
    coin_popups[:] = [created for created in coin_popups if now-created < 0.9]
    for index, created in enumerate(coin_popups[-3:]):
        popup_y = 342-(now-created)*48-index*22
        # Match the track coin: gold ellipse, pale outline and dark dollar sign.
        coin_x = kx-30
        oval(coin_x-12, popup_y-20, coin_x+12, popup_y+20,
             '#ffd24a', '#fff3a0')
        text(coin_x, popup_y, '$', 20, '#9c6500')
        text(kx+17, popup_y+2, '+1', 25, '#14243d')
        text(kx+16, popup_y, '+1', 25, '#ffe46b')
    # HUD
    rect(20,16,330,94,'#14243d')
    text(38,37,'JOYSTICK KART',21,anchor='w')
    text(38,72,f'LAP {int(distance//TRACK)+1}   COINS {coins}   HITS {hits}',13,'#fbd66b','w')
    if connected:
        text(25, 111, f'X:{sample[0]} Y:{sample[1]}  GAS:{throttle:+.2f}', 12, '#14243d', 'w')
    text(25, 130, input_status, 11, '#14243d', 'w')
    rect(760,16,1004,125,'#14243d')
    text(880,52,f'{speed:.0f} km/h',30)
    text(880,96,f'{rpm:.0f} RPM',17,'#67e8d2')
    # Direction indicator: screen y increases downwards.
    oval(922,160,1002,240,'#14243d')
    canvas.create_line(962*sx,200*sy,(962+steer*29)*sx,(200-throttle*29)*sy,
                       fill='#65e1ff',width=4,arrow=tk.LAST)
    text(512,34,'BOOST!' if boosted else ('BOOST READY' if now>=boost_ready else f'BOOST {boost_ready-now:.0f}s'),
         18,'#fff1a8')
    text(512, 70, f'TIME {math.ceil(remaining):02d}s', 24,
         '#ff7885' if remaining <= 5 else '#ffffff')
    if late_race and not finished:
        text(512, 103, f'SPEED UP!  MAX {race_pace(elapsed)[0]} km/h', 16, '#ffd24a')
    if finished:
        # Match the score's distance contribution to the displayed integer distance.
        result_distance = round(distance)
        score = coins * 100 - hits * 300 + result_distance
        rect(200, 220, 824, 425, '#14243d')
        text(512, 253, 'FINISH!', 34, '#ffd24a')
        text(512, 296, f'COINS {coins}    HITS {hits}    DISTANCE {result_distance}', 18)
        text(512, 347, f'SCORE {score}', 34, '#ffd24a')
        text(512, 398, 'Tap RESET to race again', 16, '#a9d9ee')
    elif not active:
        rect(235,250,790,340,'#14243d')
        text(512,280,'CONNECT UNO / USB',24)
        text(512,316,'Keyboard demo: arrow keys + Space',15,'#a9d9ee')
    text(20,580,'UP / DOWN: SPEED   LEFT / RIGHT: STEER   PRESS: BOOST',11,'#14243d','w')
    for x1,x2,label,callback in BUTTONS:
        item=rect(x1,550,x2,590,'#9f2941' if label == 'EXIT' else '#14243d')
        canvas.tag_bind(item,'<Button-1>',callback)
        item=text((x1+x2)/2,570,label,13)
        canvas.tag_bind(item,'<Button-1>',callback)
    # Two stronger full-screen red flashes, 150ms on / 150ms off.
    # Stipple preserves scene visibility and avoids an extra image dependency.
    if hit_flash_started is not None:
        flash_age = now-hit_flash_started
        if (0.0 <= flash_age < 0.15) or (0.30 <= flash_age < 0.45):
            canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(),
                                    fill='#e04444', outline='', stipple='gray50',
                                    tags=('hit_flash_overlay',))
            # Keep existing touch controls reachable beneath the overlay.
            canvas.tag_bind('hit_flash_overlay', '<Button-1>', flash_touch)
        elif flash_age >= 0.60:
            hit_flash_started = None
    root.after(33,frame)

def flash_touch(event):
    x = event.x*1024/max(1, canvas.winfo_width())
    y = event.y*600/max(1, canvas.winfo_height())
    if 550 <= y <= 590:
        for x1, x2, label, callback in BUTTONS:
            if x1 <= x <= x2:
                callback()
                return

root.bind('<Escape>',close)
root.bind('<KeyPress>',lambda e: keys.add(e.keysym))
root.bind('<KeyRelease>',lambda e: keys.discard(e.keysym))
root.bind('<FocusOut>',lambda e: keys.clear())
root.bind('r',reset)
root.bind('c',calibrate)
root.protocol('WM_DELETE_WINDOW',close)
threading.Thread(target=receive,daemon=True).start()
frame()
root.mainloop()
