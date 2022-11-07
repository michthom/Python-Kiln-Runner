from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from event import EventType, subscribe
from typing import Optional
import dacite


class InvalidIsolatorConfigurationException(Exception):
    pass


class IsolatorType(Enum):
    ISOLATOR_TYPE_VIRTUAL = auto()
    ISOLATOR_TYPE_RELAY_SINGLE = auto()
    ISOLATOR_TYPE_RELAY_DUAL = auto()


class IsolatorInterface(Enum):
    ISOLATOR_IF_VIRTUAL = auto()
    ISOLATOR_IF_PIN = auto()


@dataclass
class Configuration:
    """Dataclass to hold the Isolator configuration."""
    isolator_label: str
    isolator_type: IsolatorType
    isolator_interface: IsolatorInterface
    isolator_connection_1: str
    isolator_connection_2: Optional[str]

    def as_dict(self) -> dict:
        return {
            'isolator_label': self.isolator_label,
            'isolator_type': self.isolator_type.name,
            'isolator_interface': self.isolator_interface.name,
            'isolator_connection_1': self.isolator_connection_1,
            'isolator_connection_2': self.isolator_connection_1,
        }


class Isolator(ABC):
    """Abstract class to represent safety cutout systems"""

    label: str
    configuration: Configuration

    def __init__(self, configuration: Configuration):
        self.configuration = configuration

        subscribe(EventType.SCHEDULE_NEXT_SEGMENT_EVENT, self.handle_schedule_next_segment)
        subscribe(EventType.SCHEDULE_FINISHED_EVENT, self.handle_schedule_finished)

    @abstractmethod
    def __repr__(self):
        pass

    @abstractmethod
    def handle_schedule_next_segment(self, event_domain: object, data) -> None:
        pass

    @abstractmethod
    def handle_schedule_finished(self, event_domain: object, data) -> None:
        pass

    @classmethod
    def build_config(cls, configuration: dict) -> Configuration:
        if configuration is None:
            empty_configuration = Configuration(
                isolator_label='No Isolator installed. Take care.',
                isolator_type=IsolatorType.ISOLATOR_TYPE_VIRTUAL,
                isolator_interface=IsolatorInterface.ISOLATOR_IF_VIRTUAL,
                isolator_connection_1='',
                isolator_connection_2=''
            )
            return empty_configuration

        converters = {
            str: str,
            IsolatorType: lambda isolator_type: IsolatorType[isolator_type],
            IsolatorInterface: lambda isolator_if: IsolatorInterface[isolator_if]
        }

        config = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert config is not None, f"Unable to initialise Isolator"

        return config

    @classmethod
    def build_instance(cls, configuration: dict):
        config = Isolator.build_config(configuration=configuration)

        if config.isolator_type == IsolatorType.ISOLATOR_TYPE_VIRTUAL:
            return IsolatorVirtual(configuration=config)
        elif config.isolator_type == IsolatorType.ISOLATOR_TYPE_RELAY_SINGLE:
            return IsolatorRelaySingle(configuration=config)
        elif config.isolator_type == IsolatorType.ISOLATOR_TYPE_RELAY_DUAL:
            return IsolatorRelayDual(configuration=config)
        else:
            raise InvalidIsolatorConfigurationException


class IsolatorVirtual(Isolator):
    """Concrete Isolator class that models a virtual switch with no real hardware"""

    def __init__(self, configuration: Configuration):
        super().__init__(configuration)

    def __repr__(self):
        return f"IsolatorVirtual(configuration = {self.configuration.as_dict()})"

    def handle_schedule_next_segment(self, event_domain: object, data) -> None:
        # print(f"Virtual Isolator connected - system now 0.000000001% more dangerous than it was before.")
        pass

    def handle_schedule_finished(self, event_domain: object, data) -> None:
        # print(f"Virtual Isolator disengaged - system 0.000000001% safer than it was before.")
        pass


class IsolatorRelaySingle(Isolator):
    """Concrete Isolator class that models a relay-based single switch e.g. single pole contactor"""

    def __init__(self, configuration: Configuration):
        import board
        import digitalio

        super().__init__(configuration)

        # print(f"Setting up relays on pins {self.configuration.isolator_connection_1} "
        #       f"and {self.configuration.isolator_connection_2}")

        self.relay1 = digitalio.DigitalInOut(
            getattr(board.pin, self.configuration.isolator_connection_1)
        )
        self.relay1.direction = digitalio.Direction.OUTPUT
        # FIXME - need to include relay login (inverted or normal) in the config
        self.relay1.value = True

    def __repr__(self):
        return f"IsolatorVirtual(configuration = {self.configuration.as_dict()})"

    def handle_schedule_next_segment(self, event_domain: object, data) -> None:
        # print(f"Relay Isolator connected - system now rather more dangerous than it was before.")
        # FIXME - need to include relay login (inverted or normal) in the config
        self.relay1.value = False

    def handle_schedule_finished(self, event_domain: object, data) -> None:
        # FIXME - need to include relay login (inverted or normal) in the config
        # print(f"Relay Isolator disconnected - system now rather safer than it was before.")
        self.relay1.value = True


class IsolatorRelayDual(Isolator):
    """Concrete Isolator class that models a relay-based dual switch e.g. two-pole contactor"""

    def __init__(self, configuration: Configuration):
        import board
        import digitalio

        super().__init__(configuration)

        # print(f"Setting up relays on pins {self.configuration.isolator_connection_1} "
        #       f"and {self.configuration.isolator_connection_2}")

        self.relay1 = digitalio.DigitalInOut(
            getattr(board.pin, self.configuration.isolator_connection_1)
        )
        self.relay1.direction = digitalio.Direction.OUTPUT
        # FIXME - need to include relay login (inverted or normal) in the config
        self.relay1.value = True

        self.relay2 = digitalio.DigitalInOut(
            getattr(board.pin, self.configuration.isolator_connection_2)
        )
        self.relay2.direction = digitalio.Direction.OUTPUT
        self.relay2.value = True

    def __repr__(self):
        return f"IsolatorVirtual(configuration = {self.configuration.as_dict()})"

    def handle_schedule_next_segment(self, event_domain: object, data) -> None:
        self.relay1.value = False
        self.relay2.value = False

    def handle_schedule_finished(self, event_domain: object, data) -> None:
        # FIXME - need to include relay logic (inverted or normal) in the config
        self.relay1.value = True
        self.relay2.value = True
