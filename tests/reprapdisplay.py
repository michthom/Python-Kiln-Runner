from random import randint
from datetime import datetime, timedelta
from time import sleep
from pathlib import Path
from PIL import ImageFont, Image, ImageDraw, ImageFile

import RPi.GPIO as GPIO
import board
import microcontroller
import digitalio
import pwmio

rot_a = 25
rot_b = 24
last_a = False
last_b = False

candidates = []
current_candidate = 0

update_display = False


def can_fit(dt, text, font, mw, mh) -> bool:
    w, h = dt.textsize(text, font)
    return (h <= mh) and (w <= mw)


def text_fill(s, pause):
    s.clear()
    start = datetime.utcnow()
    s.send_text_to_screen("123456789012345678901", 0, 0)
    s.send_text_to_screen("123456789012345678901", 0, 30)
    s.send_text_to_screen("123456789012345678901", 0, 60)
    # s.put_text("123456789012345678901", 0, 8)
    # s.put_text("123456789012345678901", 0, 16)
    # s.put_text("123456789012345678901", 0, 24)
    # s.put_text("123456789012345678901", 0, 32)
    # s.put_text("123456789012345678901", 0, 40)
    # s.put_text("123456789012345678901", 0, 48)
    # s.put_text("123456789012345678901", 0, 56)
    s.redraw()
    end = datetime.utcnow()
    print(f"Text fill: Time taken: {end - start}")

    sleep(pause)


def line_fill(s, pause):
    s.clear()
    start = datetime.utcnow()
    for _ in range(200):
        x1 = randint(0, 127)
        y1 = randint(0, 63)
        x2 = randint(0, 127)
        y2 = randint(0, 63)
        invert = randint(0, 1)
        s.line(x1, y1, x2, y2, (invert == 0))

    s.redraw()
    end = datetime.utcnow()
    print(f"Line fill: Time taken: {end - start}")

    sleep(pause)


def callback_rotary_encoder(gpio):
    global rot_a
    global rot_b
    global last_a
    global last_b
    global candidates
    global current_candidate
    global update_display

    a = GPIO.input(rot_a)
    b = GPIO.input(rot_b)

    # Only one input should change each step - none or both == noise?
    # XOR is ^
    if not (a ^ last_a) and (b ^ last_b):
        return

    # print(f"{datetime.utcnow()} Callback for GPIO {gpio}; A: {1 if a else 0} B: {1 if b else 0}")

    if last_a and not a:
        if b:
            current_candidate = (current_candidate + len(candidates) - 1) % len(candidates)
            update_display = True
        else:
            current_candidate = (current_candidate + len(candidates) + 1) % len(candidates)
            update_display = True

    last_a = a
    last_b = b


def rebuild_image(max_width, max_height, line1, line2, line3, line4):
    global candidates
    global current_candidate

    font = ImageFont.truetype(candidates[current_candidate].as_posix(), max_height - 2)

    print(f"Font {current_candidate} of {len(candidates)}: {candidates[current_candidate].as_posix()}")

    img = Image.new(mode="1", size=(max_width, 4 * max_height), color=0)
    dt = ImageDraw.Draw(img)

    dt.text((0, 0), line1, font=font, fill=255)
    dt.text((0, max_height), line2, font=font, fill=255)
    dt.text((0, 2 * max_height), line3, font=font, fill=255)
    dt.text((0, 3 * max_height), line4, font=font, fill=255)

    return img


def do_update_display(img, disp):
    global update_display

    pixels = list(img.getdata())
    w, h = img.size
    pixels = [pixels[i * w:(i + 1) * w] for i in range(h)]

    # FIXME - need to copy these pixels to the main framebuffer
    for x in range(0, 128):
        for y in range(0, 64):
            if pixels[y][x] == 0:
                disp.plot(x, y, False)
            else:
                disp.plot(x, y, True)

    disp.redraw()

    update_display = False


def main():
    global candidates
    global current_candidate
    global update_display

    # MOSI  GPIO10, pin 19 -> LCDE (EXP1 pin 3)
    # SCLK  GPIO11, pin 23 -> LCD4 (EXP1 pin 5)
    #       GPIO13, pin 33 -> LCDRS(EXP1 pin 4)

    #       GPIO16, pin 36 -> Beeper (EXP1 pin 1)

    #       GPIO 5, pin 29 <- RotA (EXP2 pin 3)
    #       GPIO 6, pin 31 <- RotB (EXP2 pin 5)
    #       GPIO26, pin 37 <- RotBtn (EXP1 pin 2)

    #       GPIO14, pin  8 <- Reset  (EXP2 pin 8)

    pin_mosi = board.D10
    pin_sclk = board.D11
    pin_cs = board.D13

    pin_beep = board.D16

    pin_rota = board.D5
    pin_rotb = board.D6
    pin_rbtn = board.D26

    pin_reset = board.D14

    last_a = False
    last_b = False

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(rot_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(rot_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(rot_a, GPIO.IN)
    GPIO.setup(rot_b, GPIO.IN)
    GPIO.add_event_detect(rot_a, GPIO.BOTH, callback=callback_rotary_encoder, bouncetime=10)
    GPIO.add_event_detect(rot_b, GPIO.BOTH, callback=callback_rotary_encoder, bouncetime=10)

    reset = digitalio.DigitalInOut(board.D23)
    reset.direction = digitalio.Direction.INPUT
    # reset.pull = digitalio.Pull.UP
    reset.pull = None

    rot_btn = digitalio.DigitalInOut(board.D16)
    rot_btn.direction = digitalio.Direction.INPUT
    rot_btn.pull = digitalio.Pull.UP
    rot_btn.pull = None

    beeper = pwmio.PWMOut(board.D12, duty_cycle=0)
    beeper.frequency = 1760

    max_width = 128
    max_height = 16

    pause = 2

    fonts = list(Path('/usr/share/fonts/truetype/').rglob('*.[Tt][Tt][Ff]'))

    img = Image.new(mode="1", size=(max_width, 4 * max_height), color=0)
    dt = ImageDraw.Draw(img)

    #        0123456789012345
    line1 = "Stage 00 of 99"
    line2 = "Ramp 100/h to 1000F"
    line3 = "Hold 100m at 1000F"
    line4 = "Temp 1000F / 1000F"

    for f in fonts:
        font = ImageFont.truetype(f.as_posix(), max_height - 2)
        if (can_fit(dt, line1, font, max_width, max_height) and can_fit(dt, line2, font, max_width, max_height) and
                can_fit(dt, line3, font, max_width, max_height) and can_fit(dt, line4, font, max_width, max_height)):
            candidates.append(f)

    text_fill(s, pause)
    line_fill(s, pause)

    # while reset.value != False:

    current_candidate = 0

    while reset.value:
        if update_display:
            img = rebuild_image(max_width, max_height, line1, line2, line3, line4)
            do_update_display(img, s)

        if not rot_btn.value:
            print(f"Encoder button pressed. Beep!")
            beeper.duty_cycle = 2 ** 15
            sleep(0.1)
            beeper.duty_cycle = 0

    print(f"Reset button pressed. Exit program.")


if __name__ == '__main__':
    main()
