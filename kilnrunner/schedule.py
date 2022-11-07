from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional

import dacite

from event import EventType, subscribe, unsubscribe, post_event


class TemperatureScale(Enum):
    SCALE_KELVIN = auto()
    SCALE_CELSIUS = auto()
    SCALE_CENTIGRADE = SCALE_CELSIUS
    SCALE_FAHRENHEIT = auto()


class HoldTimeScale(Enum):
    HOLD_HOURS = auto()
    HOLD_MINUTES = auto()
    HOLD_SECONDS = auto()


class GradientTimeBase(Enum):
    DEGREES_PER_HOUR = auto()
    DEGREES_PER_MINUTE = auto()
    DEGREES_PER_SECOND = auto()


@dataclass
class ScheduleConfiguration:
    """Dataclass to hold the FiringSchedule configuration."""
    schedule_label: str
    temperature_scale: TemperatureScale
    hold_time_scale: HoldTimeScale
    temperature_gradient_timebase: GradientTimeBase
    segments: list

    def as_dict(self) -> dict:
        return {
            'schedule_label': self.schedule_label,
            'temperature_scale': self.temperature_scale.name,
            'hold_time_scale': self.hold_time_scale.name,
            'temperature_gradient_timebase': self.temperature_gradient_timebase.name,
            'segments': self.segments
        }


@dataclass
class SegmentConfiguration:
    """Dataclass to hold the FiringSchedule configuration."""
    segment_label: str
    target_temperature: float
    temperature_gradient: Optional[float]
    hold_time: Optional[float]

    def as_dict(self) -> dict:
        result = {
            'segment_label': self.segment_label,
            'target_temperature': self.target_temperature,
        }

        if self.temperature_gradient is not None:
            result['temperature_gradient'] = self.temperature_gradient
        if self.hold_time is not None:
            result['hold_time'] = self.hold_time

        return result


class FiringSegment(ABC):
    configuration: SegmentConfiguration
    start_temperature_kelvin: float
    latest_kiln_temperature_kelvin: float
    set_point_temperature_kelvin: float
    start_time: datetime
    predicted_elapsed_seconds: timedelta
    predicted_end_time: datetime
    actual_end_time: datetime
    is_active: bool
    temperature_target_tolerance: float

    def __init__(self, configuration: dict):
        assert configuration is not {}, f"No configuration provided to initialise {self.__class__.__name__}"

        converters = {
            str: str,
        }

        self.configuration = dacite.from_dict(
            data_class=SegmentConfiguration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        self.set_point_temperature_kelvin = 273.15
        self.latest_kiln_temperature_kelvin = 273.15
        self.temperature_target_tolerance = 5.0
        self.is_active = False

        subscribe(EventType.SCHEDULE_NEXT_SEGMENT_EVENT, self.handle_schedule_next_segment)
        subscribe(EventType.KILN_TEMPERATURE_CHANGED_EVENT, self.handle_kiln_temperature_changed)

    def __repr__(self):
        return f"{self.__class__.__name__}(configuration={self.configuration.as_dict()})"

    def handle_schedule_next_segment(self, zone: object, data) -> None:
        assert zone is None, f"No zone expected for event {EventType.SCHEDULE_NEXT_SEGMENT_EVENT}"
        if data != self:
            self.is_active = False
            return

        # print(f"Handling schedule next segment in {self.__class__.__name__} "
        #       f"with {self.latest_kiln_temperature_kelvin:.2f}")

        self.is_active = True
        self.start_time = datetime.utcnow()
        self.start_temperature_kelvin = self.latest_kiln_temperature_kelvin

        post_event(
            event_type=EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
            selector=None,
            data=self.start_temperature_kelvin
        )

        post_event(
            event_type=EventType.SEGMENT_STARTED_EVENT,
            selector=None,
            data=None
        )

    def handle_kiln_temperature_changed(self, event_domain: object, data) -> None:
        pass


class FiringSegmentRamp(FiringSegment):
    def __init__(self, configuration: dict):
        super().__init__(configuration)

        assert self.configuration.temperature_gradient is not None, \
            f"Can't create a FiringSegmentRamp without temperature_gradient configured"
        assert self.configuration is not None, f"Unable to create a Configuration for the FiringSegmentRamp"

        self.start_time = datetime.utcnow()

        self.predicted_elapsed_seconds = timedelta(
            seconds=abs(
                self.configuration.temperature_gradient *
                (self.configuration.target_temperature - self.set_point_temperature_kelvin)
            )
        )

        self.predicted_end_time = (
                self.start_time + self.predicted_elapsed_seconds
        )

    def handle_kiln_temperature_changed(self, event_domain: object, data) -> None:
        # print(f"Handling kiln temperature changed in {self.__class__.__name__} with {data:.2f}")
        self.latest_kiln_temperature_kelvin = data

        # N.B. this message is handled up by ALL segments, not just the active one...
        if not self.is_active:
            return

        self.latest_kiln_temperature_kelvin = float(data)

        # print(f"Handling temperature reading in {self.__class__.__name__} with temperature {data:.2f}")

        elapsed_time = datetime.utcnow() - self.start_time

        if self.start_temperature_kelvin < self.configuration.target_temperature:
            # Ramping up
            # print(f"Ramping up from  {self.start_temperature_kelvin:.2f} "
            #       f"to {self.configuration.target_temperature:.2f}")

            self.set_point_temperature_kelvin = min(
                self.configuration.target_temperature,
                (self.start_temperature_kelvin +
                 abs(elapsed_time.seconds * self.configuration.temperature_gradient)
                 )
            )
        else:
            # Ramping down
            # print(f"Ramping down from  {self.start_temperature_kelvin:.2f} "
            #       f"to {self.configuration.target_temperature:.2f}")

            self.set_point_temperature_kelvin = max(
                self.configuration.target_temperature,
                (
                        self.start_temperature_kelvin -
                        abs(elapsed_time.seconds * self.configuration.temperature_gradient)
                )
            )

        # print(f" Ramp: {self.set_point_temperature_kelvin = }")

        post_event(
            event_type=EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
            selector=None,
            data=self.set_point_temperature_kelvin
        )

        if abs(
                self.configuration.target_temperature
                - self.latest_kiln_temperature_kelvin
        ) < self.temperature_target_tolerance:
            self.actual_end_time = datetime.utcnow()

            print(f"Posting segment finished in {self.__class__.__name__}")
            post_event(
                event_type=EventType.SEGMENT_FINISHED_EVENT,
                selector=None,
                data=None
            )


class FiringSegmentHold(FiringSegment):
    def __init__(self, configuration: dict):
        super().__init__(configuration)

        assert self.configuration.hold_time is not None, \
            f"Can't create a FiringSegmentHold without hold_time configured"
        assert self.configuration is not None, \
            f"Unable to create a Configuration for the FiringSegmentHold"

        self.start_time = datetime.utcnow()
        self.predicted_elapsed_seconds = timedelta(seconds=self.configuration.hold_time)

        self.predicted_end_time = (
                self.start_time + timedelta(seconds=self.configuration.hold_time)
        )

    def handle_kiln_temperature_changed(self, event_domain: object, data) -> None:
        # print(f"Handling kiln temperature changed in {self.__class__.__name__} with {data:.2f}")
        self.latest_kiln_temperature_kelvin = data

        # N.B. this message is handled up by ALL segments, not just the active one...
        if not self.is_active:
            return

        self.latest_kiln_temperature_kelvin = float(data)

        # print(f"Handling temperature reading in {self.__class__.__name__}")

        # FIXME - alarm if the measured temperature is outside the acceptable hold range?
        # print(f" Hold: {self.configuration.target_temperature = }")

        post_event(
            event_type=EventType.SEGMENT_SET_POINT_CHANGED_EVENT,
            selector=None,
            data=self.configuration.target_temperature
        )

        elapsed_time = datetime.utcnow() - self.start_time

        if elapsed_time > timedelta(seconds=self.configuration.hold_time):
            self.actual_end_time = datetime.utcnow()

            post_event(
                event_type=EventType.SEGMENT_FINISHED_EVENT,
                selector=None,
                data=None
            )


class FiringSegmentAbort(FiringSegment):
    def __init__(self, configuration: dict):
        super().__init__(configuration)
        pass


class FiringSchedule:
    segments: list
    current_segment_index: int
    current_segment: FiringSegment

    @staticmethod
    def temperature_to_kelvin(value, scale) -> float:
        if scale == TemperatureScale.SCALE_KELVIN:
            return value
        if scale == TemperatureScale.SCALE_CELSIUS or scale == TemperatureScale.SCALE_CENTIGRADE:
            return value + 273.15
        if scale == TemperatureScale.SCALE_FAHRENHEIT:
            return (value - 32.0) * 5.0 / 9.0 + 273.15

    @staticmethod
    def kelvin_to_temp_scale(value, scale) -> float:
        if scale == TemperatureScale.SCALE_KELVIN:
            return value
        if scale == TemperatureScale.SCALE_CELSIUS or scale == TemperatureScale.SCALE_CENTIGRADE:
            return value - 273.15
        if scale == TemperatureScale.SCALE_FAHRENHEIT:
            return (value - 273.15) * 9.0 / 5.0 + 32.0

    @staticmethod
    def time_to_seconds(value, scale) -> float:
        if scale == HoldTimeScale.HOLD_SECONDS:
            return value
        if scale == HoldTimeScale.HOLD_MINUTES:
            return value * 60.0
        if scale == HoldTimeScale.HOLD_HOURS:
            return value * 3600.0

    @staticmethod
    def gradient_to_kelvin_per_second(value: float, scale: TemperatureScale, timebase: GradientTimeBase) -> float:
        timebase_factor = 1.0
        scale_factor = 1.0

        if timebase == GradientTimeBase.DEGREES_PER_MINUTE:
            timebase_factor = 60.0
        if timebase == GradientTimeBase.DEGREES_PER_HOUR:
            timebase_factor = 3600.0

        if scale == TemperatureScale.SCALE_FAHRENHEIT:
            scale_factor = 5.0/9.0

        result = value * scale_factor / timebase_factor

        # print(f"Segment ramp rate = {result} K/s")

        return result

    def __init__(self, configuration: dict):
        assert configuration is not {}, f"No configuration provided to initialise schedule"

        converters = {
            str: str,
            TemperatureScale: lambda x: TemperatureScale[x],
            HoldTimeScale: lambda x: HoldTimeScale[x],
            GradientTimeBase: lambda x: GradientTimeBase[x],
        }

        self.configuration = dacite.from_dict(
            data_class=ScheduleConfiguration,
            config=dacite.Config(type_hooks=converters),
            data=configuration
        )

        assert self.configuration is not None, f"Unable to create a Configuration for the schedule"

        self.segments = []

        firing_time = timedelta()

        for segment in self.configuration.segments:
            normalised_config = {'segment_label': segment.get('segment_label'),
                                 'target_temperature': self.temperature_to_kelvin(
                                     segment.get('target_temperature'),
                                     self.configuration.temperature_scale
                                 )}

            if segment.get('hold_time') is not None:
                normalised_config['hold_time'] = \
                    self.time_to_seconds(
                        segment.get('hold_time'),
                        self.configuration.hold_time_scale
                    )

            if segment.get('temperature_gradient') is not None:
                normalised_config['temperature_gradient'] = \
                    self.gradient_to_kelvin_per_second(
                        value=segment.get('temperature_gradient'),
                        scale=self.configuration.temperature_scale,
                        timebase=self.configuration.temperature_gradient_timebase
                    )

            if segment.get('hold_time') is not None and segment.get('temperature_gradient') is None:
                self.segments.append(FiringSegmentHold(configuration=normalised_config))

            if segment.get('hold_time') is None and segment.get('temperature_gradient') is not None:
                self.segments.append(FiringSegmentRamp(configuration=normalised_config))

            firing_time += self.segments[-1].predicted_elapsed_seconds

        # print(self)
        # print(f"Predicted firing time total: {firing_time}")

        subscribe(EventType.KILN_INITIALISED_EVENT, self.handle_kiln_initialised)
        subscribe(EventType.SEGMENT_FINISHED_EVENT, self.handle_segment_finished)

    def __repr__(self):
        return f"FiringSchedule(configuration={self.configuration.as_dict()})"

    def handle_kiln_initialised(self, zone: object, data):
        assert zone is None, f"No zone expected for event {EventType.KILN_INITIALISED_EVENT}"
        assert data is None, f"No data expected for event {EventType.KILN_INITIALISED_EVENT}"

        # print(f"Handling kiln initialised event in {self.__class__.__name__}")
        self.current_segment_index = 0
        self.current_segment = self.segments[self.current_segment_index]

        # print(f"Posting schedule next segment in  {self.__class__.__name__}")
        post_event(
            event_type=EventType.SCHEDULE_NEXT_SEGMENT_EVENT,
            selector=None,
            data=self.current_segment
        )

    def handle_segment_finished(self, zone: object, data):
        assert zone is None, f"No zone expected for event {EventType.SEGMENT_FINISHED_EVENT}"
        assert data is None, f"No data expected for event {EventType.SEGMENT_FINISHED_EVENT}"
        # print(f"Handling segment finished in {self.__class__.__name__}")

        self.current_segment_index += 1
        if self.current_segment_index < len(self.segments):
            self.current_segment = self.segments[self.current_segment_index]
            # print(f"Posting schedule next segment in  {self.__class__.__name__}")
            post_event(
                event_type=EventType.SCHEDULE_NEXT_SEGMENT_EVENT,
                selector=None,
                data=self.current_segment
            )
        else:
            unsubscribe(EventType.SEGMENT_FINISHED_EVENT, self.handle_segment_finished)
            # print(f"Posting schedule finished in  {self.__class__.__name__}")
            post_event(
                event_type=EventType.SCHEDULE_FINISHED_EVENT,
                selector=None,
                data=None
            )
