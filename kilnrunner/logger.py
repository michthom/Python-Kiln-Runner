import datetime
import enum
import abc
import event


class LogLevel(enum.IntEnum):
    LOGLEVEL_NONE = 0
    LOGLEVEL_ALARM = 1
    LOGLEVEL_WARNING = 2
    LOGLEVEL_INFO = 3
    LOGLEVEL_DEBUG = 4


class Logger(abc.ABC):

    @abc.abstractmethod
    def log(self, log_level: LogLevel, message: str):
        pass


class FileLogger(Logger):

    def __init__(self, maximum_log_level: LogLevel, file_path: str):
        event.subscribe(event_type=event.EventType.LOG_MESSAGE, callback_function=self.log)
        self.fd = open(file=file_path, mode="w+", encoding='utf8')
        self.maximum_log_level = maximum_log_level

    def log(self, selector: LogLevel, data: str):
        log_level = selector
        message = data
        if log_level <= self.maximum_log_level:
            if log_level == LogLevel.LOGLEVEL_INFO:
                label = " [   INFO    ] : "
            elif log_level == LogLevel.LOGLEVEL_WARNING:
                label = " [  WARNING  ] : "
            elif log_level == LogLevel.LOGLEVEL_ALARM:
                label = " [!! ALARM !!] : "
            elif log_level == LogLevel.LOGLEVEL_DEBUG:
                label = " [   DEBUG   ] : "
            else:
                label = " [   ????    ] : "
            self.fd.write(str(datetime.datetime.utcnow()) + label + message)


class ConsoleLogger(Logger):

    def __init__(self, maximum_log_level: LogLevel):
        event.subscribe(event_type=event.EventType.LOG_MESSAGE, callback_function=self.log)
        self.maximum_log_level = maximum_log_level

    def log(self, selector: LogLevel, data: str):
        log_level = selector
        message = data
        if log_level <= self.maximum_log_level:
            if log_level == LogLevel.LOGLEVEL_INFO:
                label = " [   INFO    ] : "
            elif log_level == LogLevel.LOGLEVEL_WARNING:
                label = " [  WARNING  ] : "
            elif log_level == LogLevel.LOGLEVEL_ALARM:
                label = " [!! ALARM !!] : "
            elif log_level == LogLevel.LOGLEVEL_DEBUG:
                label = " [   DEBUG   ] : "
            else:
                label = " [   ????    ] : "
            print(str(datetime.datetime.utcnow()) + label + message)
