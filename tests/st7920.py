import enum
import copy
import time
import board
import digitalio
import adafruit_bus_device.spi_device as sd


class ST7920Command(enum.IntEnum):
    BASIC_CLEAR_DISPLAY = 0x01

    BASIC_RETURN_HOME = 0x02

    BASIC_ENTRY_MODE = 0x40
    # Combine with or (|) :
    BASIC_ENTRY_DISPLAY_SHIFT = 0x01
    BASIC_ENTRY_RTL = 0x02

    BASIC_DISPLAY_CONTROL = 0x08
    # Combine with or (|) :
    BASIC_DISPLAY_ON = 0x04
    BASIC_CURSOR_ON = 0x02
    BASIC_BLINK_ON = 0x01

    BASIC_CURSOR_CONTROL = 0x10
    # Combine with or (|) :
    BASIC_CURSOR_RTL = 0x04
    BASIC_DISPLAY_SHIFT = 0x08

    BASIC_FUNCTION_SET = 0x20
    # Combine with or (|) :
    BASIC_FUNCTION_8BIT = 0x10
    BASIC_FUNCTION_TO_EXTENDED = 0x04

    BASIC_CGRAM_ADDRESS = 0x40
    # Combine with or (|) the actual address to use AC5-AC0 as LSB

    BASIC_DDRAM_ADDRESS = 0x80
    # Combine with or (|) the actual address to use AC5-AC0 as LSB

    EXTENDED_STANDBY = 0x01

    EXTENDED_SCROLL_OR_RAM_ACCESS = 0x02
    # Combine with (either but not both) using or (|) :
    EXTENDED_SCROLL_ENABLE = 0x01
    EXTENDED_CGRAM_ACCESS = 0x00

    EXTENDED_REVERSE_LINE = 0x04
    # Combine with (one of) using or (|) :
    EXTENDED_REVERSE_LINE_0 = 0x00
    EXTENDED_REVERSE_LINE_1 = 0x01
    EXTENDED_REVERSE_LINE_2 = 0x02
    EXTENDED_REVERSE_LINE_3 = 0x03

    EXTENDED_FUNCTION_SET = 0x024
    # Combine with or (|) :
    EXTENDED_FUNCTION_8BIT = 0x010
    EXTENDED_FUNCTION_TO_BASIC = 0x04
    EXTENDED_FUNCTION_GRAPHICS_ON = 0x02

    EXTENDED_SET_SCROLL_POSITION = 0x40
    # Combine with or (|) the actual address to use AC5-AC0 as LSB

    EXTENDED_GDRAM_ADDRESS = 0x80
    # Requires **two consecutive** EXTENDED_GDRAM_ADDRESS instructions
    # First
    # Combine with or (|) the vertical address to use AC5-AC0 as LSB
    # Then
    # Combine with or (|) the horizontal address to use AC3-AC0 as LSB

    """
    For datasheet, ask Google or see:
    https://www.instructables.com/The-Secrets-of-an-Inexpensive-Ubiquitous-Chinese-L/

    Instruction set 1 (RE=0: Basic instructions)

    Instruction     RS  RW  DB7 DB6 DB5 DB4 DB3 DB2 DB1 DB0 Description
    --------------------------------------------------------------------------------------------------------
    Display clear   0   0   0   0   0   0   0   0   0   1   Fill DDRAM with 0x20, set DDRAM address counter (AC) = 0x00
    Return Home     0   0   0   0   0   0   0   0   1   X   Set AC to 0x00, move cursor to 0,0. No display change
    Entry mode set  0   0   0   0   0   0   0   1   I/D S   Set cursor position and display shift for write or read
    Display control 0   0   0   0   0   0   1   D   C   B   D=1, display ON; C=1, cursor ON; B=1 Character blink ON
    Cursor display  0   0   0   0   0   1   S/C R/L X   X   Cursor position / display shift control. No DDRAM change
    Function set    0   0   0   0   1   DL  X   RE  X   X   DL=1, 8=bit; DL=0, 4-bit; RE=1, extended; RE=0, basic
    Set CGRAM addr  0   0   0   1   AC5 AC4 AC3 AC2 AC1 AC0 Set CGRAM address counter. (Refer to datasheet!)
    Set DDRAM addr  0   0   1   0   AC5 AC4 AC3 AC2 AC1 AC0 Set DDRAM address counter.
    Read busy flag  0   1   BF  AC6 AC5 AC4 AC3 AC2 AC1 AC0 Read busy flag (BF) for command completion and AC
    Write RAM       1   0   D7  D6  D5  D4  D3  D2  D1  D0  Write data to internal RAM (DDRAM / CGRAM / GDRAM)
    Read RAM        1   1   D7  D6  D5  D4  D3  D2  D1  D0  Read data from internal RAM (DDRAM / CGRAM / GDRAM)


    Instruction set 2 (RE=1: Extended instructions)

    Instruction     RS  RW  DB7 DB6 DB5 DB4 DB3 DB2 DB1 DB0 Description
    --------------------------------------------------------------------------------------------------------
    Standby         0   0   0   0   0   0   0   0   0   1   Enter standby mode
    Scroll / RAM    0   0   0   0   0   0   0   0   1   SR  SR=1, Enable vertical scroll; SR=0, Enable CGRAM access
    Entry mode set  0   0   0   0   0   0   0   1   I/D S   Set cursor position and display shift for write or read
    Reverse (lines) 0   0   0   0   0   0   0   1   R1  R0  Select 1 of 4 lines to toggle colours
    Extended funcs  0   0   0   0   1   DL  X   RE  G   0   DL=1, 8=bit; DL=0, 4-bit;
                                                            RE=1, ext; RE=0, basic; 
                                                            G=1, display ON; G=0, display OFF
    Set Scroll addr 0   0   0   1   AC5 AC4 AC3 AC2 AC1 AC0 SR=1, AC5-AC0 = the address of vertical scroll
    Set GDRAM Vaddr 0   0   1   0   AC5 AC4 AC3 AC2 AC1 AC0 Set Vertical address (must precede horizontal address
    Set GDRAM Haddr 0   0   1   0   0   0   AC3 AC2 AC1 AC0 Set Horizontal address (must follow vertical address

    SPI Data format:

    CS = High to enable transfer

    Bit 01  02  03  04  05  06  07  08  09  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24  ...
        1   1   1   1   1   RW  RS  0   D7  D6  D5  D4  0   0   0   0   D3  D2  D1  D0  0   0   0   0  
        Synchronisation - 5 bits high
                            Read (0) / Write (1)
                                Register Select (0) / Data Select (1)
                                       MSB of first byte
                                                                        LSB of first byte
    Remaining bytes are similarly split into MSB / LSB and transferred as pairs of bytes from bit 25 onwards
    """


class ST7920:
    """ST7920 graphical LCD driver for CircuitPython"""

    def __init__(self, pin_cs: board.pin, baudrate: int = 1_000_000, polarity: int = 0, phase: int = 0):
        """

        :param pin_cs: board.pin
        :param baudrate: int
        :param polarity: int [0|1]
        :param phase: int [0|1]
        """
        self.cs = digitalio.DigitalInOut(pin_cs)
        self.cs.direction = digitalio.Direction.OUTPUT

        self.baudrate = baudrate

        self.polarity = polarity

        self.phase = phase

        self.spi = board.SPI()

        self.graphics_width = 128
        self.graphics_height = 64

        self.text_width = 16
        self.text_height = 8

        self.rotation_angle_degrees = 0

        self.graphics_working_buffer = None
        self.graphics_displayed_buffer = None

        self.clear_graphics_buffer()

        self.text_working_buffer = None
        self.text_displayed_buffer = None

        self.clear_text_buffer()

        self.device = sd.SPIDevice(
            spi=self.spi,
            chip_select=self.cs,
            cs_active_value=True,
            baudrate=self.baudrate,
            polarity=self.polarity,
            phase=self.phase
        )

        self.bytes_to_write = []

        self.screen_mapped = {
            0: 0,
            1: 2,
            2: 1,
            3: 3,
            4: 4,
            5: 6,
            6: 5,
            7: 7
        }

    def setup_display(self):
        self.write_command(
            ST7920Command.BASIC_FUNCTION_SET |
            ST7920Command.BASIC_FUNCTION_8BIT
        )
        self.write_command(
            ST7920Command.BASIC_DISPLAY_CONTROL |
            ST7920Command.BASIC_DISPLAY_ON
        )

    def write_command(self, command: ST7920Command):
        """
        Formats a single command to send to the display
        :param command: ST7920Command
        :return:
        """

        """
        When starting a transmission, a start byte is required. It consists of:

        5 consecutive “1” bits (sync character). Serial transfer counter will be reset and synchronized.
        Followed by 2-bit flag that indicates:
        read/write (RW) and
        register/data selected (RS) operation.

        After receiving the sync character, RW and RS bits, every 8 bits instruction/data will be separated
        into 2 groups. Higher 4 bits (DB7~DB4) will be placed in the first section followed by 4 “0”s.
        And lower 4 bits (DB3~DB0) will be placed in the second section followed by 4 “0”s.
        """

        # print(f"0x{command:02x} ", end='')

        with self.device:
            # Command write: rs low, rw low
            # rw = 0
            # rs = 0
            # b1 = 0b11111000 | ((rw & 0x01) << 2) | ((rs & 0x01) << 1)
            # b1 = 0b11111000

            self.bytes_to_write = [0b11111000]
            self.bytes_to_write.append(command & 0xF0)  # MSB
            self.bytes_to_write.append((command & 0x0F) << 4)  # LSB

            self.spi.write(self.bytes_to_write)

    def write_data(self, data: bytearray):
        """

        :param data:
        :return:
        """

        with self.device:
            # Command write: rs low, rw low
            # rw = 0
            # rs = 1
            # b1 = 0b11111000 | ((rw & 0x01) << 2) | ((rs & 0x01) << 1)
            # b1 = 0b11111010

            self.bytes_to_write = [0b11111010]
            for byte in data:
                self.bytes_to_write.append(byte & 0xF0)
                self.bytes_to_write.append((byte & 0x0F) << 4)

            self.spi.write(self.bytes_to_write)

    # Generic methods

    def clear_all_display(self):
        self.write_command(
            ST7920Command.BASIC_FUNCTION_SET |
            ST7920Command.BASIC_FUNCTION_8BIT
        )
        self.write_command(ST7920Command.BASIC_CLEAR_DISPLAY)

    # Graphical methods

    def clear_graphics_buffer(self):
        self.graphics_working_buffer = [[0] * (self.graphics_width // 8) for _ in range(self.graphics_height)]

    def refresh_line(self, row, dx1, dx2):
        """

        :param row:
        :param dx1:
        :param dx2:
        :return:
        """

        self.write_command(
            ST7920Command.EXTENDED_FUNCTION_SET
        )

        self.write_command(
            ST7920Command.EXTENDED_FUNCTION_SET |
            ST7920Command.EXTENDED_FUNCTION_GRAPHICS_ON
        )

        self.write_command(
            # Set vertical address
            ST7920Command.EXTENDED_GDRAM_ADDRESS |
            row % 32
        )
        self.write_command(
            # Set horizontal address
            ST7920Command.EXTENDED_GDRAM_ADDRESS |
            ((dx1 // 16) + (8 if row >= 32 else 0))
        )

        self.write_data(self.graphics_working_buffer[row][dx1 // 8:(dx2 // 8) + 1])

    def refresh_graphics_display(self, dx1=0, dy1=0, dx2=127, dy2=63, full=False):
        """

        :param dx1:
        :param dy1:
        :param dx2:
        :param dy2:
        :param full:
        :return:
        """
        if self.graphics_displayed_buffer is None:  # first redraw always affects the complete LCD
            for row in range(0, self.graphics_height):
                self.refresh_line(row, 0, self.graphics_width - 1)

            # current_display_buffer is initialized here
            self.graphics_displayed_buffer = copy.deepcopy(self.graphics_working_buffer)

        else:  # redraw has been called before, since current_display_buffer is already initialized
            for row in range(dy1, dy2 + 1):
                if not full or (self.graphics_displayed_buffer[row] == self.graphics_working_buffer[row]):
                    continue
                # redraw row only if full=True or changes are detected
                self.refresh_line(row, dx1, dx2)
                fbx1 = dx1 // 8
                fbx2 = (dx2 // 8) + 1
                self.graphics_displayed_buffer[row][fbx1:fbx2] = self.graphics_working_buffer[row][fbx1:fbx2]

    def plot_pixel(self, x, y):
        if x < 0 or x >= self.graphics_width or y < 0 or y >= self.graphics_height:
            return
        # if self.rotation_angle_degrees == 0:
        self.graphics_working_buffer[y][x // 8] |= 1 << (7 - (x % 8))
        # elif self.rotation_angle_degrees == 90:
        #     self.graphics_working_buffer[x][15 - (y // 8)] |= 1 << (y % 8)
        # elif self.rotation_angle_degrees == 180:
        #     self.graphics_working_buffer[63 - y][15 - (x // 8)] |= 1 << (x % 8)
        # elif self.rotation_angle_degrees == 270:
        #     self.graphics_working_buffer[63 - x][y // 8] |= 1 << (7 - (y % 8))

    def clear_pixel(self, x, y):
        if x < 0 or x >= self.graphics_width or y < 0 or y >= self.graphics_height:
            return
        # if self.rotation_angle_degrees == 0:
        self.graphics_working_buffer[y][x // 8] &= ~(1 << (7 - (x % 8)))
        # elif self.rotation_angle_degrees == 90:
        #     self.graphics_working_buffer[x][15 - (y // 8)] &= ~(1 << (y % 8))
        # elif self.rotation_angle_degrees == 180:
        #     self.graphics_working_buffer[63 - y][15 - (x // 8)] &= ~(1 << (x % 8))
        # elif self.rotation_angle_degrees == 270:
        #     self.graphics_working_buffer[63 - x][y // 8] &= ~(1 << (7 - (y % 8)))

    def draw_line(self, x1, y1, x2, y2, erase: bool = False):
        diff_x = abs(x2 - x1)
        diff_y = abs(y2 - y1)
        shift_x = 1 if (x1 < x2) else -1
        shift_y = 1 if (y1 < y2) else -1
        err = diff_x - diff_y
        drawn = False
        while not drawn:
            if erase:
                self.clear_pixel(x1, y1)
            else:
                self.plot_pixel(x1, y1)

            if x1 == x2 and y1 == y2:
                drawn = True
                continue

            err2 = 2 * err

            if err2 > -diff_y:
                err -= diff_y
                x1 += shift_x

            if err2 < diff_x:
                err += diff_x
                y1 += shift_y

    def draw_rect(self, x1, y1, x2, y2, erase: bool = False):
        self.draw_line(x1, y1, x2, y1, erase)
        self.draw_line(x2, y1, x2, y2, erase)
        self.draw_line(x2, y2, x1, y2, erase)
        self.draw_line(x1, y2, x1, y1, erase)

    def fill_rect(self, x1, y1, x2, y2, erase: bool = False):
        for y in range(y1, y2 + 1):
            self.draw_line(x1, y, x2, y, erase)

    # Text methods

    def clear_text_buffer(self):
        self.text_working_buffer = [[" "] * self.text_width for _ in range(self.text_height)]

    def refresh_text_display(self):
        for line in range(self.text_height):
            screen_line = self.screen_mapped[line]
            self.send_text_to_screen(x=0, y=screen_line, length=self.text_width)

    def clear_text_only(self):
        self.write_command(
            ST7920Command.BASIC_FUNCTION_SET |
            ST7920Command.BASIC_FUNCTION_8BIT
        )
        self.write_command(
            ST7920Command.BASIC_RETURN_HOME
        )
        for line in range(self.text_height):
            for pos in range(self.text_width):
                self.bytes_to_write.append(ord(" "))
        self.write_data(bytearray(self.bytes_to_write))

    def smooth_scroll(self, down: bool = True):
        self.write_command(
            ST7920Command.EXTENDED_FUNCTION_SET |
            ST7920Command.EXTENDED_FUNCTION_8BIT
        )
        self.write_command(
            ST7920Command.EXTENDED_SCROLL_OR_RAM_ACCESS |
            ST7920Command.EXTENDED_SCROLL_ENABLE
        )

        if down:
            positions = range(0, 36, 4)
        else:
            positions = range(32, -4, -4)

        for scroll_position in positions:
            self.write_command(ST7920Command.EXTENDED_SET_SCROLL_POSITION | scroll_position)
            time.sleep(0.25)

    def text_page_select(self, show_page_2: bool = False):
        if show_page_2:
            position = 0x20
        else:
            position = 0x00
        self.write_command(
            ST7920Command.EXTENDED_FUNCTION_SET |
            ST7920Command.EXTENDED_FUNCTION_8BIT
        )
        self.write_command(
            ST7920Command.EXTENDED_SCROLL_OR_RAM_ACCESS |
            ST7920Command.EXTENDED_SCROLL_ENABLE
        )
        self.write_command(ST7920Command.EXTENDED_SET_SCROLL_POSITION | position)

    def reverse_colour_lines(self):
        # This is perhaps a bit pointless as reversing line 0 (in memory) reverses
        # the colours for lines 0 and 2 (on my version of the display)
        self.write_command(
            ST7920Command.EXTENDED_FUNCTION_SET |
            ST7920Command.EXTENDED_FUNCTION_8BIT
        )
        for line in range(4):
            self.write_command(ST7920Command.EXTENDED_REVERSE_LINE | line)
            time.sleep(0.5)
            self.write_command(ST7920Command.EXTENDED_REVERSE_LINE | line)
            time.sleep(0.5)

    def put_text_in_buffer(self, text: str, x: int, y: int, wrap: bool = False):
        current_line = y
        current_pos = x

        for character in text:
            if current_pos == self.text_width:
                if not wrap:
                    return

                current_pos = 0
                current_line += 1
                if current_line == self.text_height:
                    return

            self.text_working_buffer[current_line][current_pos] = character
            current_pos += 1

    def send_text_to_screen(self, x: int, y: int, length: int):
        # Display data RAM (DDRAM) - character display addresses
        #      0x00 - 0x0F;   0x10 - 0x1F;  0x20 - 0x2F;  0x30 - 0x3F
        # maps to display positions (x, y)
        #     (0,0)-(15,0);  (0,2)-(15,2); (0,1)-(15,1); (0,3)-(15,3)
        #
        # Display data RAM (DDRAM) - character display addresses
        #      0x40 - 0x4F;   0x50 - 0x5F;  0x60 - 0x6F;  0x70 - 0x7F
        # maps to display positions (x, y)
        #     (0,4)-(15,4);  (0,6)-(15,6); (0,5)-(15,5); (0,7)-(15,7)
        #
        # (But you need to set scroll position to 32 to see these values displayed)

        """

        :param x:
        :param y:
        :param length:
        :return:
        """

        self.write_command(
            ST7920Command.BASIC_FUNCTION_SET |
            ST7920Command.BASIC_FUNCTION_8BIT
        )
        self.write_command(
            ST7920Command.BASIC_DDRAM_ADDRESS |
            (x // 2 + self.screen_mapped[y] * 8)
        )

        self.bytes_to_write = []

        if (x % 2) == 1:
            self.bytes_to_write.append(ord(" "))

        # 0 <= x <= self.width
        # 0 <= len(text) < unlimited
        # index from 0 to min(self.width - x, len(text))
        pos_max = min(self.text_width - x, length)
        for pos in range(pos_max):
            self.bytes_to_write.append(
                ord(self.text_working_buffer[y][x + pos])
            )

        self.write_data(bytearray(self.bytes_to_write))


def main():
    """
    # MOSI  GPIO10
    # SCLK  GPIO11
    # CS

    GPIO13
    """

    s = ST7920(pin_cs=board.D13)

    s.setup_display()

    s.clear_all_display()

    s.put_text_in_buffer(text="Hello", x=0, y=0)
    s.put_text_in_buffer(text="World", x=1, y=1)
    s.put_text_in_buffer(text="Pikiln Lives !!!!!!!!!!!!!!!!!!!!!!!!!!", x=2, y=2, wrap=True)
    s.put_text_in_buffer(text="(cough)", x=3, y=3)

    s.refresh_text_display()
    time.sleep(2)

    # FIXME - text wrap is not yet working.
    # s.clear_all_display()
    #
    # s.put_text(text="Hello", x=0, y=0, wrap=False)
    # s.put_text(text="World", x=1, y=1, wrap=False)
    # s.put_text(text="Pikiln Lives !!!!!!!!!!!!!!!!!!!!!!!!!!", x=2, y=2, wrap=True)
    # s.put_text(text="(cough)", x=3, y=3, wrap=False)
    # time.sleep(10)

    # s.text_page_select(show_page_2=True)
    # time.sleep(1)
    #
    # s.text_page_select(show_page_2=False)
    # time.sleep(1)
    #
    # s.smooth_scroll(down=True)
    # time.sleep(1)
    #
    # s.smooth_scroll(down=False)
    # time.sleep(1)
    #
    # s.reverse_colour_lines()
    # time.sleep(1)

    s.clear_graphics_buffer()
    s.draw_rect(8, 8, 120, 56)

    s.refresh_graphics_display(full=True)
    time.sleep(2)

    s.draw_line(8, 8, 120, 56)
    s.draw_line(8, 56, 120, 8)

    s.refresh_graphics_display(full=True)
    time.sleep(2)

    s.clear_text_only()
    time.sleep(2)

    s.clear_all_display()


if __name__ == '__main__':
    main()

"""
For datasheet, ask Google or see:
https://www.instructables.com/The-Secrets-of-an-Inexpensive-Ubiquitous-Chinese-L/

Instruction set 1 (RE=0: Basic instructions)

Instruction     RS  RW  DB7 DB6 DB5 DB4 DB3 DB2 DB1 DB0 Description
--------------------------------------------------------------------------------------------------------
Display clear   0   0   0   0   0   0   0   0   0   1   Fill DDRAM with 0x20, set DDRAM address counter (AC) to 0x00
Return Home     0   0   0   0   0   0   0   0   1   X   Set AC to 0x00, move cursor to 0,0. No display change
Entry mode set  0   0   0   0   0   0   0   1   I/D S   Set cursor position and display shift for write or read
Display control 0   0   0   0   0   0   1   D   C   B   D=1, display ON; C=1, cursor ON; B=1 Character blink ON
Cursor display  0   0   0   0   0   1   S/C R/L X   X   Cursor position / display shift control. No DDRAM change
Function set    0   0   0   0   1   DL  X   RE  X   X   DL=1, 8=bit; DL=0, 4-bit; RE=1, extended; RE=0, basic
Set CGRAM addr  0   0   0   1   AC5 AC4 AC3 AC2 AC1 AC0 Set CGRAM address counter. (Refer to datasheet!)
Set DDRAM addr  0   0   1   0   AC5 AC4 AC3 AC2 AC1 AC0 Set DDRAM address counter.
Read busy flag  0   1   BF  AC6 AC5 AC4 AC3 AC2 AC1 AC0 Read busy flag (BF) for command completion and AC
Write RAM       1   0   D7  D6  D5  D4  D3  D2  D1  D0  Write data to internal RAM (DDRAM / CGRAM / GDRAM)
Read RAM        1   1   D7  D6  D5  D4  D3  D2  D1  D0  Read data from internal RAM (DDRAM / CGRAM / GDRAM)


Instruction set 2 (RE=1: Extended instructions)

Instruction     RS  RW  DB7 DB6 DB5 DB4 DB3 DB2 DB1 DB0 Description
--------------------------------------------------------------------------------------------------------
Standby         0   0   0   0   0   0   0   0   0   1   Enter standby mode
Scroll / RAM    0   0   0   0   0   0   0   0   1   SR  SR=0, Enable vertical scroll position. SR=0, Enable CGRAM access
Entry mode set  0   0   0   0   0   0   0   1   I/D S   Set cursor position and display shift for write or read
Reverse (lines) 0   0   0   0   0   0   0   1   R1  R0  Select 1 of 4 lines to toggle colours
Extended funcs  0   0   0   0   1   DL  X   RE  G   0   DL=1, 8=bit; DL=0, 4-bit;
                                                        RE=1, ext; RE=0, basic; 
                                                        G=1, display ON; G=0, display OFF
Set Scroll addr 0   0   0   1   AC5 AC4 AC3 AC2 AC1 AC0 SR=1, AC5-AC0 = the address of vertical scroll
Set GDRAM Vaddr 0   0   1   0   AC5 AC4 AC3 AC2 AC1 AC0 Set Vertical address (must precede horizontal address
Set GDRAM Haddr 0   0   1   0   0   0   AC3 AC2 AC1 AC0 Set Horizontal address (must follow vertical address

SPI Data format:

CS = High to enable transfer

Bit 01  02  03  04  05  06  07  08  09  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24  ...
    1   1   1   1   1   RW  RS  0   D7  D6  D5  D4  0   0   0   0   D3  D2  D1  D0  0   0   0   0  
    Synchronisation - 5 bits high
                        Read (0) / Write (1)
                            Register Select (0) / Data Select (1)
                                   MSB of first byte
                                                                    LSB of first byte
Remaining bytes are similarly split into MSB / LSB and transferred as pairs of bytes from bit 25 onwards
"""
