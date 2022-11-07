import time
import board
import digitalio

print("press the button!")

relay1 = digitalio.DigitalInOut(board.D22)
relay1.direction = digitalio.Direction.OUTPUT

relay2 = digitalio.DigitalInOut(board.D27)
relay2.direction = digitalio.Direction.OUTPUT

button = digitalio.DigitalInOut(board.D26)
button.direction = digitalio.Direction.INPUT
button.switch_to_input(pull=digitalio.Pull.UP)

state = 0
while True:
    if button.value == 0:
        state = (state + 1) % 4
        # Button is pressed
        relay1state = state & 0x01
        relay2state = (state & 0x02) // 2
        relay1.value = relay1state
        relay2.value = relay2state
        print('\nState is: ', relay1state, relay2state)
    else:
        print('.', end='', flush=True)
    time.sleep(0.5)
