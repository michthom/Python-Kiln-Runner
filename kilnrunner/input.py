from abc import ABC, abstractmethod


class InputDevice(ABC):

    @abstractmethod
    def setup_input_device(self):
        pass
