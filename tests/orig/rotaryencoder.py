import time
import board
import digitalio

button = digitalio.DigitalInOut(board.D16)
button.direction = digitalio.Direction.INPUT
button.switch_to_input(pull=digitalio.Pull.UP)

REclk = digitalio.DigitalInOut(board.D13)
REclk.direction = digitalio.Direction.INPUT
REclk.switch_to_input(pull=digitalio.Pull.UP)

REdt = digitalio.DigitalInOut(board.D12)
REdt.direction = digitalio.Direction.INPUT
REdt.switch_to_input(pull=digitalio.Pull.UP)

count = 0

OLDclk = REclk.value
OLDdt = REdt.value

while True:
    CURRENTclk = REclk.value
    if CURRENTclk != OLDclk:
        CURRENTdt = REdt.value
        if CURRENTdt != CURRENTclk:
            count -= 1
        else:
            count += 1
        print(count)
        time.sleep(0.1)
