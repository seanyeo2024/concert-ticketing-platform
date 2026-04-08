"""
amqp_publisher.py
Local utility for publishing messages to the ctms_topic exchange.
"""
import json
import os

import pika


def get_connection():
    credentials = pika.PlainCredentials(
        os.environ.get("RABBITMQ_USER", "ctms"),
        os.environ.get("RABBITMQ_PASSWORD", "ctms_pass"),
    )
    params = pika.ConnectionParameters(
        host=os.environ.get("RABBITMQ_HOST", "localhost"),
        port=int(os.environ.get("RABBITMQ_PORT", 5672)),
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    return pika.BlockingConnection(params)


def publish(routing_key: str, payload: dict) -> None:
    exchange = os.environ.get("RABBITMQ_EXCHANGE", "ctms_topic")
    connection = get_connection()
    channel = connection.channel()
    channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
    channel.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
        ),
    )
    connection.close()
