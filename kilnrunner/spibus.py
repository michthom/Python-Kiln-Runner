import board


class SpiBus:
    def __init__(self):
        self.spi = board.SPI()


# See https://stackoverflow.com/questions/13642654/good-practice-sharing-resources-between-modules
# The instance below is initialised only the **first** time the module is imported, so other modules
# can share the instance by also importing this module then referring to/through it.
# E.g.
#       import spibus
#       self.spi = spibus.instance.spi

instance = SpiBus()
