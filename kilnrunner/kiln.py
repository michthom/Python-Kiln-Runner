from threading import Thread, Event
from event import EventType, subscribe, post_event
from dataclasses import dataclass
from zone import Zone
from display import Display
from isolator import Isolator
from typing import List
import dacite


class InvalidConfiguration(Exception):
    pass


@dataclass
class Configuration:
    """Dataclass to hold the Kiln configuration."""
    kiln_label: str
    zones: List[dict]

    def as_dict(self) -> dict:
        return {
            'kiln_label': self.kiln_label,
            'zones': self.zones
        }


class RepeatingTimer(Thread):
    def __init__(self, event):
        Thread.__init__(self)
        self.stopped = event
        self.running = False

    def run(self):
        self.running = True
        while not self.stopped.wait(1.0):
            post_event(
                event_type=EventType.KILN_UPDATE_TRIGGERED_EVENT,
                selector=self,
                data=None
            )


class Kiln(object):
    configuration: Configuration
    zones: List[Zone]
    latest_temperature_kelvin: float
    timer = RepeatingTimer
    halt_periodic_updates: Event

    def __repr__(self):
        return f"Kiln(configuration={self.configuration.as_dict()})"

    def __init__(self, configuration: dict):
        assert configuration is not {}, f"No kiln_parameters provided to initialise kiln"
        # pprint.pprint(configuration)

        converters = {
            str: str,
        }

        self.configuration = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert self.configuration is not None, f"Unable to create a Configuration for the kiln"

        self.zones = []
        self.latest_temperature_kelvin = 273.15

        for zone_configuration in configuration.get('zones'):
            self.zones.append(Zone(zone_configuration))

        self.isolator = Isolator.build_instance(configuration.get('isolator'))
        self.display = Display.build_instance(configuration.get('display'))

        self.halt_periodic_updates = Event()
        self.timer = RepeatingTimer(self.halt_periodic_updates)

        subscribe(EventType.ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT, self.handle_zone_temperature_update)

    def start_regular_updates(self):
        if not self.timer.running:
            self.timer.start()

    def stop_regular_updates(self):
        self.halt_periodic_updates.set()

    def handle_zone_temperature_update(self, event_domain: object, data):
        if event_domain in self.zones:
            # print(f"Handling temperature reading from {event_domain.__class__.__name__} "
            #       f"in {self.__class__.__name__} with {data:.2f}")

            # FIXME - need to calculate average over multiple zones
            self.latest_temperature_kelvin = float(data)

            post_event(
                event_type=EventType.KILN_TEMPERATURE_CHANGED_EVENT,
                selector=None,
                data=self.latest_temperature_kelvin
            )
