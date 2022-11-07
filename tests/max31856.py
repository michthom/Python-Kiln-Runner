# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import board
import digitalio
import adafruit_max31856

spi = board.SPI()

cs = digitalio.DigitalInOut(board.D21)
cs.direction = digitalio.Direction.INPUT

flt = digitalio.DigitalInOut(board.D20)
flt.direction = digitalio.Direction.INPUT

max31856 = adafruit_max31856.MAX31856(spi=spi, cs=cs)

max31856.temperature_thresholds = (0.0, 1000.0)
max31856.reference_temperature_thresholds = (0.0, 35.0)

while True:
    tempC = max31856.temperature
    tempF = tempC * 9 / 5 + 32
    print("Temperature: {} C {} F ".format(tempC, tempF))
    if not flt.value:
        print(max31856.fault)
    time.sleep(2.0)
