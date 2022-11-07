import time
import board
import digitalio
from rpi_hardware_pwm import HardwarePWM
from simple_pid import PID
from adafruit_debouncer import Debouncer


def current_milli_time():
    return round(time.time() * 1000)


def servo_duty_cycle(percent):
    # 0 <= percent <= 100
    # servo duty cycle is 5% - 10% (fsd)
    return 3.0 + 9.1 * percent / 100.0


# Initialise rotary encoder
button = digitalio.DigitalInOut(board.D16)
button.direction = digitalio.Direction.INPUT
button.switch_to_input(pull=digitalio.Pull.UP)

REclk = digitalio.DigitalInOut(board.D23)
REclk.direction = digitalio.Direction.INPUT
REclk.switch_to_input(pull=digitalio.Pull.UP)
REclkEdge = Debouncer(REclk)

REdt = digitalio.DigitalInOut(board.D12)
REdt.direction = digitalio.Direction.INPUT
REdt.switch_to_input(pull=digitalio.Pull.UP)

count = sdc = 0
lasttime = current_milli_time()
lastCLK = dtValue = REclk.value

# Initialize PWM output for the servo (on pin D18):
# /boot/config.txt
#   dtoverlay=pwm-2chan,pin=18,func=2,pin2=13,func2=4
# PWM channel 0 = pin18
# PWM channel 1 = pin13

print("Initialising PWM")

pid = PID(0.75, 0.01, 0.05, setpoint=50)
pid.output_limits = (0, 100)

servo = HardwarePWM(1, hz=50)
servo.start(count)

print("Entering main loop...")

control = 0.0
count = 0
while True:
    if current_milli_time() > lasttime + 5:
        lasttime = current_milli_time()
        newValue = REclk.value
        if newValue != lastCLK:
            lastCLK = newValue
            dtValue = REdt.value
            if dtValue == newValue:
                count += 1
            else:
                count -= 1
            count = min(100, max(0, count))
            print(control, count)

        control = pid(count)
        print(control)
        sdc = servo_duty_cycle(count)
        servo.change_duty_cycle(sdc)
