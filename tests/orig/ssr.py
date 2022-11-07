import time
import board
import microcontroller
import digitalio
import pwmio

relay1 = digitalio.DigitalInOut(getattr(microcontroller.pin, 'D16'))
relay1.direction = digitalio.Direction.OUTPUT
relay1.value = False

ssr_frequency = 10.0

# Initialize PWM output for the servo (on pin D18):
servo = pwmio.PWMOut(board.D18, frequency=ssr_frequency)


# Create a function to simplify setting PWM duty cycle for the servo:
def old_servo_duty_cycle(pulse_ms, frequency):
    period_ms = 1.0 / frequency * 1000.0
    duty_cycle = int(pulse_ms / (period_ms / 65535.0))
    return duty_cycle


def servo_duty_cycle(percent=0.0):
    duty_cycle = int((percent / 100.0) * 65535.0)
    return duty_cycle


# Main loop will run forever moving between 1.0 and 2.0 mS long pulses:
value = 0
while True:
    print(f"  {value}%")
    servo.duty_cycle = servo_duty_cycle(percent=value)
    time.sleep(2)
    value = (value + 10) % 110
