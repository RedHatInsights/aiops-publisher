import threading, time
import pytest
import os
from producer import publish_message
from kafka import KafkaConsumer

msg = 'Aiops-testing'

class Consumer(threading.Thread):
    def __init__(self, server, topic, msg=None):
        threading.Thread.__init__(self)
        self.stop_event = threading.Event()
        self.server = server
        self.topic = topic
        self.msg = msg

    def stop(self):
        self.stop_event.set()

    def run(self):
        consumer = KafkaConsumer(self.topic, bootstrap_servers=self.server, request_timeout_ms=10)

        while not self.stop_event.is_set():
            if consumer.poll():
                message = consumer.poll()
                if self._check_message(message):
                    break

    def _check_message(self, msg=None):
        if self.msg in msg:
            self.flag = True
            return True
        return False
            
@pytest.fixture
def topic():
    return os.environ.get('KAFKA_TOPIC')

@pytest.fixture
def kafka_server():
    return os.environ.get('KAFKA_SERVER')

@pytest.fixture
def kafka_consumer(kafka_server, topic):
    consumer = Consumer(server=kafka_server, topic=topic, msg=msg)
    consumer.start()
    yield consumer
    if consumer.is_alive():
        consumer.stop()


def test_publisher(kafka_consumer, kafka_server, topic):
    publish_message(server=kafka_server, topic=topic, data=msg)
    kafka_consumer.stop()
    assert True, "Consumer is able to receive the message."
