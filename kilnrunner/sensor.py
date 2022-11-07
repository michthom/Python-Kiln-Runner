from event import EventType, subscribe, post_event
from heater import Heater

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
import dacite


class InvalidSensorConfigurationException(Exception):
    pass


class SensorType(Enum):
    SENSOR_TYPE_VIRTUAL = auto()
    SENSOR_TYPE_MAX31856 = auto()


class SensorInterfaceType(Enum):
    SENSOR_IF_SPI = auto()
    SENSOR_IF_I2C = auto()
    SENSOR_IF_VIRTUAL = auto()


@dataclass
class Configuration:
    """Dataclass to hold the Sensor configuration."""
    sensor_label: str
    sensor_type: SensorType
    sensor_interface: SensorInterfaceType
    # FIXME I don't believe str is the right type here...
    sensor_connection: str
    fault_connection: str

    def as_dict(self) -> dict:
        return {
            'sensor_label': self.sensor_label,
            'sensor_type': self.sensor_type.name,
            'sensor_interface': self.sensor_interface.name,
            'sensor_connection': self.sensor_connection
        }


class Sensor(ABC):
    """Abstract class to represent temperature sensors"""

    label: str
    configuration: Configuration
    zone: object
    latest_temperature_kelvin: float

    def __init__(self, configuration: Configuration, zone: object):
        self.configuration = configuration

        self.zone = zone

        self.latest_temperature_kelvin = 273.15
        subscribe(EventType.KILN_UPDATE_TRIGGERED_EVENT, self.handle_zone_update_triggered)

    def __repr__(self):
        return f"{self.__class__.__name__}(configuration={self.configuration.as_dict()})"

    @abstractmethod
    def get_temperature_kelvin(self) -> float:
        pass

    @abstractmethod
    def handle_zone_update_triggered(self, event_domain: object, data) -> None:
        pass

    @classmethod
    def build_config(cls, configuration: dict) -> Configuration:
        assert configuration is not {}, f"No parameters provided to initialise Sensor"

        converters = {
            str: str,
            SensorType: lambda sensor_type: SensorType[sensor_type],
            SensorInterfaceType: lambda sensor_interface_type: SensorInterfaceType[sensor_interface_type]
        }

        config = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert config is not None, f"Unable to initialise Sensor"
        return config

    @classmethod
    def build_instance(cls, configuration: dict, zone):
        config = Sensor.build_config(configuration=configuration)

        if config.sensor_type == SensorType.SENSOR_TYPE_MAX31856:
            return SensorMAX31856(configuration=config, zone=zone)
        elif config.sensor_type == SensorType.SENSOR_TYPE_VIRTUAL:
            return SensorVIRTUAL(configuration=config, zone=zone)
        else:
            raise InvalidSensorConfigurationException


class SensorVIRTUAL(Sensor):
    """Concrete Sensor class that models a virtual sensor with no real hardware"""

    _stored_heat: float
    heater_instance: Optional[Heater]

    def __init__(self, configuration: Configuration, zone: object):
        super().__init__(configuration, zone)
        subscribe(EventType.ZONE_HEATER_POWER_CHANGED_EVENT, self.handle_heater_power_changed)

    def get_temperature_kelvin(self):
        return self._stored_heat / 50.0

    def handle_heater_power_changed(self, event_domain: object, data):
        if event_domain != self.zone:
            return

        # print(f"Handling Heater power changed in {self.__class__.__name__} with power set to {data}")

        heater_power_percent = float(data)

        lost_to_environment = (self.latest_temperature_kelvin - 273.15) * 0.005
        gained_from_heater = heater_power_percent * 0.15

        self.latest_temperature_kelvin -= lost_to_environment
        self.latest_temperature_kelvin += gained_from_heater

        # print(f"Adjusted temperature to {self.latest_temperature_kelvin}")

        post_event(
            event_type=EventType.ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT,
            selector=self.zone,
            data=self.latest_temperature_kelvin
        )

    def handle_zone_update_triggered(self, zone: object, data):
        pass


class SensorMAX31856(Sensor):
    """Concrete Sensor class that controls a real MAX31856 sensor"""

    def __init__(self, configuration: Configuration, zone: object):
        import board
        import digitalio
        import adafruit_max31856

        super().__init__(configuration, zone)

        self.spi = board.SPI()

        sensor_pin = getattr(board.pin, self.configuration.sensor_connection)
        fault_pin = getattr(board.pin, self.configuration.fault_connection)

        self.cs = digitalio.DigitalInOut(sensor_pin)
        self.cs.direction = digitalio.Direction.OUTPUT

        self.fault = digitalio.DigitalInOut(fault_pin)
        self.fault.direction = digitalio.Direction.INPUT

        self.thermocouple = adafruit_max31856.MAX31856(spi=self.spi, cs=self.cs)

        self.thermocouple.temperature_thresholds = (0.0, 1000.0)
        self.thermocouple.reference_temperature_thresholds = (0.0, 35.0)

    def read_sensor(self) -> float:
        """Code to actually read the sensor (in Celsius)"""

        # FIXME - need more robust error handling than this!!
        if self.fault.value is False:
            # Ignore but announce voltage faults - EMI / poor shielding?

            current_faults = self.thermocouple.fault

            if current_faults["voltage"]:
                print(f"Thermocouple under-/over-voltage fault - check grounding / EMI shielding")

            if (current_faults["cj_high"] or
                    current_faults["cj_low"] or
                    current_faults["cj_range"] or
                    current_faults["tc_high"] or
                    current_faults["tc_low"] or
                    current_faults["tc_range"] or
                    current_faults["open_tc"]):
                print(f"Aborting immediately - sensor fault detected:")
                print(
                    "Temps: %.2f :: cj: %.2f"
                    % (self.thermocouple.temperature, self.thermocouple.reference_temperature)
                )
                print("Thresholds:")
                print("Temp low: %.2f high: %.2f" % self.thermocouple.temperature_thresholds)
                print("CJ low: %.2f high: %.2f" % self.thermocouple.reference_temperature_thresholds)
                print("")
                print("Faults:")
                print(
                    "Temp Hi: %s | CJ Hi: %s"
                    % (current_faults["tc_high"], current_faults["cj_high"])
                )
                print(
                    "Temp Low: %s | CJ Low: %s"
                    % (current_faults["tc_low"], current_faults["cj_low"])
                )
                print(
                    "Temp Range: %s | CJ Range: %s"
                    % (current_faults["tc_range"], current_faults["cj_range"])
                )
                print("")
                print(
                    "Open Circuit: %s Voltage Over/Under: %s"
                    % (current_faults["open_tc"], current_faults["voltage"])
                )

                post_event(
                    event_type=EventType.SCHEDULE_FINISHED_EVENT,
                    selector=None,
                    data=None
                )

                """
                E.g.
                {
                    'cj_range': False,
                    'tc_range': True,
                    'cj_high': False,
                    'cj_low': False,
                    'tc_high': True,
                    'tc_low': False,
                    'voltage': False,
                    'open_tc': True
                }
                """

        return self.thermocouple.temperature

    def read_cold_jn(self) -> float:
        """Code to actually read the cold junction temperature (in Celsius)"""
        return self.thermocouple.reference_temperature

    def get_temperature_kelvin(self) -> float:
        """Return the reported temperature normalised in Kelvin"""
        return self.read_sensor() + 273.15

    def get_ambient_temperature_kelvin(self) -> float:
        """Return the cold junction temperature normalised in Kelvin"""
        return self.read_cold_jn() + 273.15

    def handle_zone_update_triggered(self, zone: object, data):
        self.latest_temperature_kelvin = self.get_temperature_kelvin()

        post_event(
            event_type=EventType.ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT,
            selector=self.zone,
            data=self.latest_temperature_kelvin
        )
