from collections import defaultdict
from enum import Enum, auto

_subscribers = defaultdict(list)


class EventType(Enum):
    # selector=None, data=None
    KILN_INITIALISED_EVENT = auto()
    KILN_UPDATE_TRIGGERED_EVENT = auto()
    KILN_TEMPERATURE_CHANGED_EVENT = auto()

    # selector=None, data=None
    SCHEDULE_NEXT_SEGMENT_EVENT = auto()
    SCHEDULE_FINISHED_EVENT = auto()
    COOL_DOWN_FINISHED_EVENT = auto()

    # selector=None, data=None
    SEGMENT_STARTED_EVENT = auto()
    SEGMENT_SET_POINT_CHANGED_EVENT = auto()
    SEGMENT_FINISHED_EVENT = auto()

    ZONE_SENSOR_TEMPERATURE_CHANGED_EVENT = auto()
    ZONE_CONTROLLER_OUTPUT_CHANGED_EVENT = auto()
    ZONE_HEATER_POWER_CHANGED_EVENT = auto()

    # selector = logger.LogLevel, data = str
    LOG_MESSAGE = auto()


def subscribe(event_type: EventType, callback_function):
    # No need to check if the event type exists already thanks to collections.defaultdict(list)
    # https://docs.python.org/3/library/collections.html#collections.defaultdict

    # print(f"\nSubscribing to event {event_type} with handler {callback_function}")
    _subscribers[event_type].append(callback_function)


def unsubscribe(event_type: EventType, callback_function):
    # No need to check if the event type exists already thanks to collections.defaultdict(list)
    # https://docs.python.org/3/library/collections.html#collections.defaultdict

    subscriber = _subscribers[event_type].index(callback_function)
    if subscriber is not None:
        # print(f"\nUnsubscribing from event {event_type} for handler {callback_function}")
        _subscribers[event_type].pop(subscriber)


def post_event(event_type: EventType, selector: object, data: object):
    # No need to check if the event type is missing thanks to collections.defaultdict(list)

    for callback_function in _subscribers[event_type]:
        # print(f"Calling handler {callback_function} with data = {data}")
        callback_function(selector, data)
