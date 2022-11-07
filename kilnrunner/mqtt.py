from paho.mqtt import client as mqtt_client
from event import EventType, subscribe
from schedule import FiringSegment
from random import randint


class MqttClient:

    def __init__(self):

        self.broker_hostname = 'homeassistant.local'
        self.broker_port = 1883
        self.base_topic = 'homeassistant/sensor/kiln'
        self.client_id = f'python-mqtt-{randint(0, 1000)}'
        self.username = 'mqtt_kiln'
        self.password = 'eeU4!!Tr9ewW'
        self.client = None

        subscribe(EventType.SCHEDULE_NEXT_SEGMENT_EVENT, self.handle_schedule_next_segment)
        subscribe(EventType.KILN_TEMPERATURE_CHANGED_EVENT, self.handle_kiln_temperature_changed)
        subscribe(EventType.SEGMENT_SET_POINT_CHANGED_EVENT, self.handle_segment_setpoint_changed)
        subscribe(EventType.ZONE_HEATER_POWER_CHANGED_EVENT, self.handle_zone_heater_power_changed)

        self.client = self.connect_mqtt()
        # self.publish(subtopic="info", message="Initialised MQTT client")

    def handle_schedule_next_segment(self, zone: object, segment: FiringSegment):
        assert zone is None, f"No zone expected for event {EventType.SCHEDULE_NEXT_SEGMENT_EVENT}"
        self.publish(subtopic="segment", message=segment.configuration.segment_label)

    def handle_kiln_temperature_changed(self, zone: object, data: float):
        assert zone is None, f"No zone expected for event {EventType.KILN_TEMPERATURE_CHANGED_EVENT}"
        self.publish(subtopic="temperature", message=f"{data}")

    def handle_segment_setpoint_changed(self, zone: object, data: float):
        assert zone is None, f"No zone expected for event {EventType.SEGMENT_SET_POINT_CHANGED_EVENT}"
        self.publish(subtopic="setpoint", message=f"{data}")

    def handle_zone_heater_power_changed(self, zone: object, data: float):
        assert zone is not None, f"Zone required for event {EventType.ZONE_HEATER_POWER_CHANGED_EVENT}"
        self.publish(subtopic="power", message=f"{data}")

    def connect_mqtt(self) -> mqtt_client:
        def on_connect(the_client, userdata, flags, rc):
            if rc != 0:
                print("Failed to connect, return code %d\n", rc)

        # Set Connecting Client ID
        client = mqtt_client.Client(self.client_id)
        client.username_pw_set(self.username, self.password)
        client.on_connect = on_connect
        client.connect(self.broker_hostname, self.broker_port)
        return client

    def publish(self, subtopic: str, message: str):
        topic = f"{self.base_topic}/{subtopic}"
        result = self.client.publish(topic, message)
        # result: [0, 1]
        status = result[0]
        if status != 0:
            print(f"Failed to send message to topic {self.base_topic}")
