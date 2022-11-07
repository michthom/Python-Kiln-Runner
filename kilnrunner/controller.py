from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from event import EventType, subscribe, post_event
import dacite


class InvalidControllerConfigurationException(Exception):
    pass


class ControllerType(Enum):
    CONTROLLER_TYPE_VIRTUAL = auto()
    CONTROLLER_TYPE_PID = auto()


class ControllerInterface(Enum):
    CONTROLLER_IF_SPI = auto()
    CONTROLLER_IF_I2C = auto()
    CONTROLLER_IF_VIRTUAL = auto()


@dataclass
class Configuration:
    """Dataclass to hold the Controller configuration."""
    controller_label: str
    controller_type: ControllerType
    controller_interface: ControllerInterface
    controller_connection: str

    def as_dict(self) -> dict:
        return {
            'controller_label': self.controller_label,
            'controller_type': self.controller_type.name,
            'controller_interface': self.controller_interface.name,
            'controller_connection': self.controller_connection
        }


class Controller(ABC):
    """Abstract class to represent heating controllers"""

    label: str
    configuration: Configuration
    event_domain: object
    set_point: float
    output: float
    latest_temperature_kelvin: float

    def __init__(self, configuration: Configuration, event_domain: object):
        self.configuration = configuration
        self.event_domain = event_domain
        self.set_point = 0.0
        self.output = 0.0
        subscribe(EventType.KILN_UPDATE_TRIGGERED_EVENT, self.handle_zone_update_trigger)
        subscribe(EventType.SEGMENT_SET_POINT_CHANGED_EVENT, self.handle_segment_set_point_changed)
        subscribe(EventType.ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT, self.handle_zone_temperature_changed)

    @abstractmethod
    def __repr__(self):
        pass

    @abstractmethod
    def handle_zone_update_trigger(self, event_domain: object, data) -> None:
        pass

    @abstractmethod
    def handle_segment_set_point_changed(self, event_domain: object, data) -> None:
        pass

    @abstractmethod
    def handle_zone_temperature_changed(self, event_domain: object, data) -> None:
        pass

    @classmethod
    def build_config(cls, configuration: dict) -> Configuration:
        assert configuration is not {}, f"No parameters provided to initialise Controller"

        converters = {
            str: str,
            ControllerType: lambda controller_type: ControllerType[controller_type],
            ControllerInterface: lambda controller_interface: ControllerInterface[controller_interface]
        }

        config = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert config is not None, f"Unable to initialise Controller"

        return config

    @classmethod
    def build_instance(cls, configuration: dict, zone: object):
        config = Controller.build_config(configuration=configuration)

        if config.controller_type == ControllerType.CONTROLLER_TYPE_PID:
            return ControllerPID(configuration=config, zone=zone)
        elif config.controller_type == ControllerType.CONTROLLER_TYPE_VIRTUAL:
            return ControllerVIRTUAL(configuration=config, zone=zone)
        else:
            raise InvalidControllerConfigurationException


class ControllerVIRTUAL(Controller):
    """Concrete Controller class that models a virtual controller with no real hardware"""

    def __init__(self, configuration: Configuration, zone: object):
        super().__init__(configuration, zone)
        self.latest_temperature_kelvin = 273.15

    def __repr__(self):
        return f"ControllerVIRTUAL(configuration = {self.configuration.as_dict()})"

    def handle_segment_set_point_changed(self, event_domain: object, data) -> None:
        # print(f"Handling Controller set point change in {self.__class__.__name__} with {data = }")
        self.set_point = float(data)

    def handle_zone_temperature_changed(self, event_domain: object, data) -> None:
        # Only process events for our own domain (Zone)
        if self.event_domain != event_domain:
            return

        self.latest_temperature_kelvin = data

    def handle_zone_update_trigger(self, event_domain: object, data) -> None:
        # Only process events for our own domain (Zone)
        if self.event_domain != event_domain:
            return

        if self.set_point > self.latest_temperature_kelvin:
            # Enable overshoot?
            self.output = min(100.0, max(20.0, self.set_point - self.latest_temperature_kelvin))
        else:
            self.output = 0.0

        # print(f"Handling Zone update in {self.__class__.__name__}, output set to {self.output}")

        post_event(
            event_type=EventType.ZONE_CONTROLLER_OUTPUT_CHANGED_EVENT,
            selector=self.event_domain,
            data=self.output
        )


class ControllerPID(Controller):
    """Concrete Controller class that manages a real PID controller"""

    def __init__(self, configuration: Configuration, zone: object):
        from simple_pid import PID

        super().__init__(configuration, zone)
        self.latest_temperature_kelvin = self.set_point

        # FIXME - PID parameters need to be variable / supplied in configuration
        self.pid = PID(
            Kp=120.0,
            Ki=0.008,
            Kd=30.0,
            output_limits=(0.0, 100.0)
        )

    def __repr__(self):
        return f"ControllerPID(configuration = {self.configuration.as_dict()})"

    def handle_zone_update_trigger(self, event_domain: object, data) -> None:

        self.output = self.pid(self.latest_temperature_kelvin)

        post_event(
            event_type=EventType.ZONE_CONTROLLER_OUTPUT_CHANGED_EVENT,
            selector=self.event_domain,
            data=self.output
        )

    def handle_segment_set_point_changed(self, event_domain: object, data) -> None:
        self.set_point = float(data)
        self.pid.setpoint = self.set_point

    def handle_zone_temperature_changed(self, event_domain: object, data) -> None:
        # Only process events for our own domain (Zone)
        if self.event_domain != event_domain:
            return

        self.latest_temperature_kelvin = data
