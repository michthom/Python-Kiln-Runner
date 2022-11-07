"""
Usage:
  kilnrunner -h
  kilnrunner (--configpath=CONFIGPATH)
             (--schedulepath=SCHEDULEPATH)

Options:
  -h --help                                     Show this help text
  -c CONFIGPATH --configpath=CONFIGPATH         Path to the configuration in YAML format
  -s SCHEDULEPATH --schedulepath=SCHEDULEPATH   Path to the schedule definitions in YAML format
"""
import time
from datetime import datetime
from docopt import docopt
from yaml import safe_load, parser

from kiln import Kiln
from zone import Zone
from schedule import FiringSchedule, FiringSegment
from event import EventType, subscribe, post_event
import logger
from mqtt import MqttClient


class Application:

    def __init__(self, arguments: dict):
        self.arguments = arguments
        self.kiln_configuration = self.parsefile(self.arguments, '--configpath')
        self.firing_schedule = self.parsefile(self.arguments, '--schedulepath')

        self.mqtt = MqttClient()

        self.kiln = Kiln(self.kiln_configuration)
        self.schedule = FiringSchedule(self.firing_schedule)

        # FIXME - need to get logging working properly
        self.log = logger.ConsoleLogger(maximum_log_level=logger.LogLevel.LOGLEVEL_INFO)
        post_event(
            event_type=EventType.LOG_MESSAGE,
            selector=logger.LogLevel.LOGLEVEL_INFO,
            data="Test message info")
        post_event(
            event_type=EventType.LOG_MESSAGE,
            selector=logger.LogLevel.LOGLEVEL_WARNING,
            data="Test message warning")
        post_event(
            event_type=EventType.LOG_MESSAGE,
            selector=logger.LogLevel.LOGLEVEL_ALARM,
            data="Test message alarm")
        post_event(
            event_type=EventType.LOG_MESSAGE,
            selector=logger.LogLevel.LOGLEVEL_DEBUG,
            data="Test message debug")

        self.set_point_kelvin = 0.0
        self.heater_power_percent = 0.0

        self.running = False

        subscribe(EventType.SCHEDULE_NEXT_SEGMENT_EVENT, self.handle_schedule_next_segment)
        subscribe(EventType.SEGMENT_SET_POINT_CHANGED_EVENT, self.handle_segment_set_point_changed)
        subscribe(EventType.KILN_TEMPERATURE_CHANGED_EVENT, self.handle_kiln_temperature_changed)
        subscribe(EventType.ZONE_HEATER_POWER_CHANGED_EVENT, self.handle_heater_power_changed)
        subscribe(EventType.SCHEDULE_FINISHED_EVENT, self.handle_schedule_finished)
        subscribe(EventType.COOL_DOWN_FINISHED_EVENT, self.handle_cool_down_finished)

    @staticmethod
    def parsefile(args: dict, arg_path: str) -> dict:
        path = args.get(arg_path)
        if path is not None:
            try:
                with open(path) as f:
                    configuration = safe_load(f)
                    return configuration
            except FileNotFoundError:
                # print(f"File \"{path}\" not found.")
                return {}
            except parser.ParserError:
                # print(f"Unable to parse file \"{path}\".")
                return {}
        else:
            # print(f"File path parameter \"{arg_path}\" not found.")
            return {}

    def run(self):
        self.running = True

        self.kiln.start_regular_updates()

        post_event(
            event_type=EventType.KILN_INITIALISED_EVENT,
            selector=None,
            data=None
        )

    def cool_down(self):
        self.running = True

    @staticmethod
    def handle_schedule_next_segment(selector: Zone, data: FiringSegment) -> None:
        zone = selector
        segment = data
        assert zone is None, f"No zone expected for event {EventType.SCHEDULE_NEXT_SEGMENT_EVENT}"
        # print(f"*** __main__  Starting new segment *** {segment.configuration.segment_label}")
        # print(f"Date/Timestamp\tSet Point\tTemp Now\tHeater Power")
        post_event(event_type=EventType.LOG_MESSAGE,
                   selector=logger.LogLevel.LOGLEVEL_DEBUG,
                   data=f"Handling schedule next segment in __main__(): {segment.configuration.segment_label}")

    def handle_segment_set_point_changed(self, zone: object, set_point_kelvin: float) -> None:
        assert zone is None, f"No zone expected for event {EventType.SEGMENT_SET_POINT_CHANGED_EVENT}"
        self.set_point_kelvin = set_point_kelvin

    def handle_heater_power_changed(self, zone: Zone, heater_power_percent: float) -> None:
        assert zone is not None, f"Zone expected for event {EventType.ZONE_HEATER_POWER_CHANGED_EVENT}"
        self.heater_power_percent = heater_power_percent

    def handle_kiln_temperature_changed(self, zone: object, temperature_kelvin: float) -> None:
        assert zone is None, f"No zone expected for event {EventType.KILN_TEMPERATURE_CHANGED_EVENT}"
        s = self.schedule
        print(f"{datetime.utcnow()}\t"
              f"{s.kelvin_to_temp_scale(self.set_point_kelvin, s.configuration.temperature_scale):.2f}\t"
              f"{s.kelvin_to_temp_scale(temperature_kelvin, s.configuration.temperature_scale):.2f}\t"
              f"{self.heater_power_percent:.2f}")

    def handle_schedule_finished(self, zone: object, data: object) -> None:
        assert zone is None, f"No zone expected for event {EventType.SCHEDULE_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {EventType.SCHEDULE_FINISHED_EVENT}"
        self.running = False
        # print(f"*** __main__ schedule complete ***")

    def handle_cool_down_finished(self, zone: object, data: object) -> None:
        assert zone is None, f"No zone expected for event {EventType.COOL_DOWN_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {EventType.COOL_DOWN_FINISHED_EVENT}"
        self.running = False
        self.kiln.stop_regular_updates()
        self.kiln.display.clear_display()
        # print(f"*** __main__ cool down complete ***")

    def is_running(self) -> bool:
        return self.running


def main():
    app_arguments = docopt(__doc__, version='Kilnrunner v0.1')
    app = Application(arguments=app_arguments)

    try:
        app.run()
        while app.is_running():
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\nManual abort via ^C")
        post_event(
            event_type=EventType.SCHEDULE_FINISHED_EVENT,
            selector=None,
            data=None
        )

    try:
        app.cool_down()
        while app.is_running():
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\nManual abort via ^C")

        # FIXME this should be in response to temperature back near ambient

        post_event(
            event_type=EventType.COOL_DOWN_FINISHED_EVENT,
            selector=None,
            data=None
        )


if __name__ == "__main__":
    main()
