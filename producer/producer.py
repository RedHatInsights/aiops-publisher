from kafka import KafkaProducer, producer

import json

def publish_message(server: str, topic: str, data: dict) -> dict:
    """Produces a message with a topic on the message bus."""
    producer = KafkaProducer(bootstrap_servers=server)
    json_string = json.dumps(data)
    databytes = json_string.encode()
    future =  producer.send(topic, databytes)
    result = future.get()
    return result

