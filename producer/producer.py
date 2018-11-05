import json

from kafka import KafkaProducer


def publish_message(server: str, topic: str, data: dict) -> dict:
    """Produce a message with a topic on the message bus."""
    producer = KafkaProducer(bootstrap_servers=server)
    json_string = json.dumps(data)
    databytes = json_string.encode()
    future = producer.send(topic, databytes)

    return future.get()
