import board
from enum import Enum, auto
from dataclasses import dataclass
from abc import ABC, abstractmethod
import dacite
import event
import schedule


class InvalidDisplayConfigurationException(Exception):
    pass


class DisplayType(Enum):
    DISPLAY_TYPE_VIRTUAL = auto()
    DISPLAY_TYPE_ST7920 = auto()


class DisplayInterface(Enum):
    DISPLAY_IF_PIN = auto()
    DISPLAY_IF_SPI = auto()
    DISPLAY_IF_I2C = auto()
    DISPLAY_IF_VIRTUAL = auto()


@dataclass
class Configuration:
    """Dataclass to hold the Heater configuration."""
    display_label: str
    display_type: DisplayType
    display_interface: DisplayInterface
    # FIXME I don't believe str is the right type here...
    display_connection: str

    def as_dict(self) -> dict:
        return {
            'display_label': self.display_label,
            'display_type': self.display_type.name,
            'display_interface': self.display_interface.name,
            'display_connection': self.display_connection
        }


class Display(ABC):
    def __init__(self, configuration: Configuration):
        self.configuration = configuration
        self.current_target_temperature_kelvin = None
        self.current_measured_temperature_kelvin = None
        self.current_segment_name = None
        self.current_segment_target_temperature_kelvin = None
        self.current_segment_temperature_gradient = None
        self.current_segment_temperature_gradient_units = None
        self.current_segment_hold_quantity = None
        self.current_segment_hold_units = None
        self.current_target_temp = None

    def __repr__(self):
        return f"{self.__class__.__name__}(configuration={self.configuration.as_dict()})"

    @classmethod
    def build_config(cls, configuration: dict) -> Configuration:
        assert configuration is not {}, f"No parameters provided to initialise Display"

        converters = {
            str: str,
            DisplayType: lambda display_type: DisplayType[display_type],
            DisplayInterface: lambda display_interface: DisplayInterface[display_interface]
        }

        config = dacite.from_dict(
            data_class=Configuration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert config is not None, f"Unable to initialise Display"

        return config

    @classmethod
    def build_instance(cls, configuration: dict):
        config = Display.build_config(configuration=configuration)

        # Subclasses should register a constructor with their type,
        # so we just call them and don't need this if/else
        # return factories[config.display_type](configuration=config)
        # or something like that.

        if config.display_type == DisplayType.DISPLAY_TYPE_VIRTUAL:
            return DisplayVIRTUAL(configuration=config)
        elif config.display_type == DisplayType.DISPLAY_TYPE_ST7920:
            return DisplayST7920(configuration=config)
        else:
            raise InvalidDisplayConfigurationException

    @abstractmethod
    def initialise(self):
        pass

    @abstractmethod
    def clear_display(self):
        pass


class DisplayVIRTUAL(Display):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        event.subscribe(
            event_type=event.EventType.KILN_TEMPERATURE_CHANGED_EVENT,
            callback_function=self.handle_kiln_temperature_update
        )
        event.subscribe(
            event_type=event.EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
            callback_function=self.handle_segment_setpoint_changed
        )
        event.subscribe(
            event_type=event.EventType.SCHEDULE_FINISHED_EVENT,
            callback_function=self.handle_schedule_finished
        )
        event.subscribe(
            event_type=event.EventType.SCHEDULE_NEXT_SEGMENT_EVENT,
            callback_function=self.handle_schedule_next_segment
        )

    def initialise(self):
        pass

    def handle_kiln_temperature_update(self, event_domain: object, data):
        # subscribe to KILN_TEMPERATURE_CHANGED_EVENT
        # Display current measured temperature
        assert event_domain is None, f"No zone expected for event {event.EventType.KILN_TEMPERATURE_CHANGED_EVENT}"
        self.current_measured_temperature_kelvin = data

    def handle_schedule_next_segment(self, event_domain: object, segment: schedule.FiringSegment):
        assert event_domain is None, f"No zone expected for event {event.EventType.SCHEDULE_NEXT_SEGMENT_EVENT}"
        self.current_segment_name = segment.configuration.segment_label

    def handle_segment_setpoint_changed(self, event_domain: object, data):
        # subscribe to SEGMENT_SET_POINT_CHANGED_EVENT
        # Display current target temperature
        # Better to display margin of error maybe?
        assert event_domain is None, f"No zone expected for event {event.EventType.SEGMENT_SET_POINT_CHANGED_EVENT}"
        self.current_segment_target_temperature_kelvin = data

    def handle_schedule_finished(self, event_domain: object, data):
        # subscribe to SCHEDULE_FINISHED_EVENT
        # Display "Cool down" segment message
        assert event_domain is None, f"No zone expected for event {event.EventType.SCHEDULE_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {event.EventType.SCHEDULE_FINISHED_EVENT}"
        self.current_segment_name = "Cooling down"

    def clear_display(self):
        pass


class DisplayST7920(Display):

    def __init__(self, configuration: Configuration):
        import st7920

        super().__init__(configuration)
        event.subscribe(
            event_type=event.EventType.KILN_TEMPERATURE_CHANGED_EVENT,
            callback_function=self.handle_kiln_temperature_update
        )
        event.subscribe(
            event_type=event.EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
            callback_function=self.handle_segment_setpoint_changed
        )
        event.subscribe(
            event_type=event.EventType.SCHEDULE_FINISHED_EVENT,
            callback_function=self.handle_schedule_finished
        )
        event.subscribe(
            event_type=event.EventType.SCHEDULE_NEXT_SEGMENT_EVENT,
            callback_function=self.handle_schedule_next_segment
        )

        self.cs = getattr(board, configuration.display_connection)
        self.baudrate = 1_000_000
        self.polarity = 0
        self.phase = 0
        self.width = 128
        self.height = 64

        self.display = st7920.ST7920(pin_cs=self.cs, polarity=self.polarity, phase=self.phase, baudrate=self.baudrate)

    def handle_kiln_temperature_update(self, event_domain: object, data):
        # subscribe to KILN_TEMPERATURE_CHANGED_EVENT
        # Display current measured temperature
        assert event_domain is None, f"No zone expected for event {event.EventType.KILN_TEMPERATURE_CHANGED_EVENT}"
        self.current_measured_temperature_kelvin = data
        self.display.clear_text_buffer()
        self.display.put_text_in_buffer(f"Temperature now:", x=0, y=0)
        temp_c = self.current_measured_temperature_kelvin - 273.15
        temp_f = temp_c * (9 / 5) + 32.0
        self.display.put_text_in_buffer(f"{temp_c:6.1f}C  {temp_f:6.1f}F", x=0, y=1)
        self.display.put_text_in_buffer(f"[{self.current_segment_name}]", x=0, y=2, wrap=True)
        self.display.refresh_text_display()

    def handle_schedule_next_segment(self, event_domain: object, segment: schedule.FiringSegment):
        assert event_domain is None, f"No zone expected for event {event.EventType.SCHEDULE_NEXT_SEGMENT_EVENT}"
        self.current_segment_name = segment.configuration.segment_label
        self.display.put_text_in_buffer(f"[{self.current_segment_name}]", x=0, y=3)
        self.display.refresh_text_display()

    def handle_segment_setpoint_changed(self, event_domain: object, data):
        # subscribe to SEGMENT_SET_POINT_CHANGED_EVENT
        # Display current target temperature
        # Better to display margin of error maybe?
        # self.current_segment_target_temperature_kelvin = data
        # self.display.put_text_in_buffer(f"Target: {self.current_segment_target_temperature_kelvin:8.1f}", x=1, y=0)
        assert event_domain is None, f"No zone expected for event {event.EventType.SEGMENT_SET_POINT_CHANGED_EVENT}"
        assert data is not None, f"Data expected for event {event.EventType.SEGMENT_SET_POINT_CHANGED_EVENT}"

    def handle_schedule_finished(self, event_domain: object, data):
        # subscribe to SCHEDULE_FINISHED_EVENT
        # Display "Cool down" segment message
        # self.current_segment_name = "Cooling down"
        # self.display.put_text_in_buffer(f"[{self.current_segment_name}]", x=2, y=0)
        assert event_domain is None, f"No zone expected for event {event.EventType.SCHEDULE_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {event.EventType.SCHEDULE_FINISHED_EVENT}"

    def initialise(self):
        self.display.setup_display()
        self.display.clear_all_display()

    def clear_display(self):
        self.display.clear_all_display()
