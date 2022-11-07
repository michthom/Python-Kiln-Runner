from abc import ABC, abstractmethod
from dataclasses import dataclass
import dacite
from enum import Enum, auto

from event import EventType, subscribe, post_event


class InvalidSensorConfigurationException(Exception):
    pass


class HeaterType(Enum):
    HEATER_TYPE_VIRTUAL = auto()
    HEATER_TYPE_PWM = auto()


class HeaterInterface(Enum):
    HEATER_IF_PIN = auto()
    HEATER_IF_SPI = auto()
    HEATER_IF_I2C = auto()
    HEATER_IF_VIRTUAL = auto()


@dataclass
class Configuration:
    """Dataclass to hold the Heater configuration."""
    heater_label: str
    heater_type: HeaterType
    heater_interface: HeaterInterface
    # FIXME I don't believe str is the right type here...
    heater_connection: str
    heater_max_power_watts: float

    def as_dict(self) -> dict:
        return {
            'heater_label': self.heater_label,
            'heater_type': self.heater_type.name,
            'heater_interface': self.heater_interface.name,
            'heater_connection': self.heater_connection
        }


class Heater(ABC):
    """Abstract class to represent heating elements"""

    label: str
    power_percent: float
    configuration: Configuration
    event_domain: object

    def __init__(self, configuration: Configuration, event_domain: object):
        self.configuration = configuration
        self.event_domain = event_domain
        self.power_percent = 0.0
        self.max_power_watts = 0.0
        subscribe(EventType.ZONE_CONTROLLER_OUTPUT_CHANGED_EVENT, self.handle_controller_output_change)
        subscribe(EventType.SCHEDULE_FINISHED_EVENT, self.handle_schedule_finished)

    def __repr__(self):
        return f"{self.__class__.__name__}(configuration={self.configuration.as_dict()})"

    @abstractmethod
    def handle_schedule_finished(self, event_domain: object, data) -> None:
        pass

    @abstractmethod
    def handle_controller_output_change(self, event_domain: object, data) -> None:
        if self.event_domain == event_domain:
            # print(f"Handling Controller output change in {self.__class__.__name__}")
            # Only process events for our own domain (Zone)
            self.power_percent = float(data)
            post_event(
                event_type=EventType.ZONE_HEATER_POWER_CHANGED_EVENT,
                selector=self.event_domain,
                data=self.power_percent
            )

    @classmethod
    def build_config(cls, configuration: dict) -> Configuration:
        assert configuration is not {}, f"No parameters provided to initialise Heater"

        converters = {
            str: str,
            HeaterType: lambda heater_type: HeaterType[heater_type],
            HeaterInterface: lambda heater_interface: HeaterInterface[heater_interface]
        }

        config = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert config is not None, f"Unable to initialise Heater"

        return config

    @classmethod
    def build_instance(cls, configuration: dict, zone: object):
        config = Heater.build_config(configuration=configuration)

        if config.heater_type == HeaterType.HEATER_TYPE_VIRTUAL:
            return HeaterVIRTUAL(configuration=config, zone=zone)
        elif config.heater_type == HeaterType.HEATER_TYPE_PWM:
            return HeaterSSRPWM(configuration=config, zone=zone)
        else:
            raise InvalidSensorConfigurationException


class HeaterVIRTUAL(Heater):
    """Concrete Heater class that models a virtual element with no real hardware"""

    def __init__(self, configuration: Configuration, zone: object):
        super().__init__(configuration, zone)
        pass

    def handle_controller_output_change(self, event_domain: object, data) -> None:
        # Only process events for our own domain
        if self.event_domain != event_domain:
            return

        # print(f"Handling Controller output change in {self.__class__.__name__} with {data = }")
        self.power_percent = float(data)
        post_event(
            event_type=EventType.ZONE_HEATER_POWER_CHANGED_EVENT,
            selector=self.event_domain,
            data=self.power_percent
        )

    def handle_schedule_finished(self, event_domain: object, data) -> None:
        self.power_percent = 0.0

        post_event(
            event_type=EventType.ZONE_HEATER_POWER_CHANGED_EVENT,
            selector=self.event_domain,
            data=0.0
        )


class HeaterSSRPWM(Heater):
    """Concrete Heater class that models a real element driven by a SSR using PWM"""

    def __init__(self, configuration: Configuration, zone: object):
        import board
        import pwmio

        super().__init__(configuration, zone)
        # set to 5Hz to ensure that the possible values 0,10,20... 100% map to whole sine wave
        # cycles. If switching half waves, could end up with DC bias.
        self.ssr_frequency_hz = 5

        pin = getattr(board.pin, self.configuration.heater_connection)
        self.ssr = pwmio.PWMOut(
            pin=pin,
            frequency=self.ssr_frequency_hz,
            duty_cycle=0.0
        )

        # Duty cycle is a 16 bit value 0 (0%) to 65535 (100%)

    def handle_controller_output_change(self, event_domain: object, power_percent: float) -> None:
        if self.event_domain == event_domain:
            # print(f"Handling Controller output change in {self.__class__.__name__}")
            # Only process events for our own domain

            # Quantised the requested power to 10% increments, to ensure that the
            # SSR is turned on for an integral number of full sine waves, avoiding DC bias
            self.power_percent = int(power_percent // 10) * 10
            # print(f"power_level = {power_level}")

            self.ssr.duty_cycle = int((self.power_percent / 100.0) * 65535.0)
            # print(f"self.ssr.duty_cycle = {self.ssr.duty_cycle}")

            post_event(
                event_type=EventType.ZONE_HEATER_POWER_CHANGED_EVENT,
                selector=self.event_domain,
                data=self.power_percent
            )

    def handle_schedule_finished(self, event_domain: object, data) -> None:
        self.power_percent = 0.0
        self.ssr.duty_cycle = 0.0

# FIXME - CRITICAL - Need to turn off the SSR if the program aborts!
