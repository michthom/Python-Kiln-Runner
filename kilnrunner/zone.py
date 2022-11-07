from dataclasses import dataclass
import dacite

from event import EventType, subscribe, post_event
from controller import Controller, ControllerType
from sensor import Sensor, SensorType
from heater import Heater, HeaterType


class InvalidZoneConfigurationException(Exception):
    pass


@dataclass
class Configuration:
    """Dataclass to hold the Zone configuration."""
    zone_label: str
    sensor_config: dict
    controller_config: dict
    heater_config: dict
    maximum_temperature_kelvin: float

    def as_dict(self) -> dict:
        return {
            'zone_label': self.zone_label,
            'sensor_config': self.sensor_config,
            'controller_config': self.controller_config,
            'heater_config': self.heater_config,
            'maximum_temperature_kelvin': self.maximum_temperature_kelvin
        }


class Zone(object):
    """Represents a heating zone within a kiln"""

    configuration: Configuration
    sensor: Sensor
    controller: Controller
    heater: Heater
    latest_temperature_kelvin: float

    def __repr__(self):
        return (f"Zone("
                f"configuration={self.configuration.as_dict()}, "
                f"sensor={self.sensor}, "
                f"controller={self.controller}, "
                f"heater={self.heater}"
                f")")

    def __init__(self, configuration: dict):
        assert configuration is not {}, f"No zone parameters provided to initialise zone"

        converters = {
            str: str,
            SensorType: lambda sensor_type: SensorType[sensor_type],
            ControllerType: lambda controller_type: ControllerType[controller_type],
            HeaterType: lambda heater_type: HeaterType[heater_type]
        }

        self.configuration = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert self.configuration is not None, f"Unable to create a Configuration for the zone"

        self.latest_temperature_kelvin = 273.15

        self.sensor = Sensor.build_instance(
            configuration=self.configuration.sensor_config,
            zone=self
        )

        self.controller = Controller.build_instance(
            configuration=self.configuration.controller_config,
            zone=self
        )

        self.heater = Heater.build_instance(
            configuration=self.configuration.heater_config,
            zone=self
        )

        subscribe(EventType.SEGMENT_STARTED_EVENT, self.handle_segment_started)
        subscribe(EventType.SEGMENT_FINISHED_EVENT, self.handle_segment_finished)
        subscribe(EventType.ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT, self.handle_temperature_reading)
        subscribe(EventType.SCHEDULE_FINISHED_EVENT, self.handle_schedule_finished)

    def handle_segment_started(self, zone: object, data):
        assert zone is None, f"No zone expected for event {EventType.SEGMENT_STARTED_EVENT}"
        assert data is None, f"No data expected for event {EventType.SEGMENT_STARTED_EVENT}"
        # print(f"Handling segment start in {self.__class__.__name__}")
        post_event(event_type=EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
                   selector=None,
                   data=self.latest_temperature_kelvin)

    def handle_segment_finished(self, zone: object, data):
        assert zone is None, f"No zone expected for event {EventType.SEGMENT_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {EventType.SEGMENT_FINISHED_EVENT}"

        # print(f"Handling segment finishing in {self.__class__.__name__}")

    def handle_temperature_reading(self, zone: object, data):
        if zone == self:
            # print(f"Handling temperature reading in {self.__class__.__name__}")
            self.latest_temperature_kelvin = data

    def handle_schedule_finished(self, zone: object, data):
        assert zone is None, f"No zone expected for event {EventType.SCHEDULE_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {EventType.SCHEDULE_FINISHED_EVENT}"
        # print(f"Handling schedule finishing in {self.__class__.__name__}")
