from kafka import KafkaProducer, producer

def publish_message(server: str, topic: str, data: str) -> dict:
    """Produces a message with a topic on the message bus"""
    producer = KafkaProducer(bootstrap_servers=server)
    databytes = bytes(data, 'utf-8')
    future =  producer.send(topic, databytes)
    result = future.get()
    return result

