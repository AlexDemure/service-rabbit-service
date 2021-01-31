import asyncio
import logging
import os
import copy
import json
from typing import Any
from uuid import uuid4
from time import sleep

import aio_pika
from functools import partial
from aio_pika.channel import Channel
from aio_pika.message import IncomingMessage, Message


class BaseRMQ:

    login: str = None
    password: str = None
    host: str = None
    port: str = None

    connection = None
    channel = None

    def __init__(self, login: str, password: str, host: str, port: str):
        self.login = login
        self.password = password
        self.host = host
        self.port = port

    def generate_url_connection(self) -> str:
        return f"amqp://{self.login}:{self.password}@{self.host}:{self.port}/"

    @staticmethod
    def serialize(data: Any) -> bytes:
        return json.dumps(data).encode()

    @staticmethod
    def deserialize(data: bytes) -> Any:
        return json.loads(data)

    async def connect_to_broker(self) -> Channel:
        """
        Общая точка для получения канала для работы с брокером. Возвращает канал к брокеру RabbitMQ.
        """
        retries = 0
        while not self.connection:
            conn_str = self.generate_url_connection()
            print(f"Trying to create connection to broker: {conn_str}")
            try:
                self.connection = await aio_pika.connect_robust(conn_str)
                print(f"Connected to broker ({type(self.connection)} ID {id(self.connection)}")
            except Exception as e:
                if retries > 5:
                    raise Exception
                retries += 1
                print(f"Can't connect to broker {retries} time({e.__class__.__name__}:{e}). Will retry in 5 seconds...")
                sleep(5)

        if not self.channel:
            print("Trying to create channel to broker")
            self.channel = await self.connection.channel()
            print("Got a channel to broker")

        return self.channel


class MessageQueue(BaseRMQ):

    async def send(self, queue_name: str, data: Any):
        message = Message(
            body=self.serialize(data),
            content_type="application/json",
            correlation_id=str(uuid4()),
        )
        await self.channel.default_exchange.publish(message, queue_name)

    async def consume_queue(self, func, queue_name: str, auto_delete_queue: bool = False):
        """Регистрация очереди в брокере и получение IncomingMessage в функцию."""
        # Создание queues в рабите
        queue = await self.channel.declare_queue(queue_name, auto_delete=auto_delete_queue, durable=True)

        # Вроде как постоянное итерирование по очереди в ожидании месседжа.
        # Есть алтернативный вариант получения месседжа через queue.get(timeout=N)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                logging.debug(f'Received message body: {message.body}')
                await func(message)


class RPC(BaseRMQ):

    futures = {}

    @staticmethod
    async def cancel_consumer(queue, consumers):
        for key, val in consumers.items():
            await queue.cancel(key)

    def on_response(self, message: IncomingMessage):
        future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)
        message.ack()

    async def call(self, queue_name: str, **kwargs):
        # Создание уникальной очереди на которую будет возвращен ответ из другого сервиса.
        callback_queue = await self.channel.declare_queue(exclusive=True, auto_delete=True, durable=True)

        # Метод класса который обрабатывает ответ
        await callback_queue.consume(self.on_response)

        # Копирование консумеров для удаления очереди из раббита
        consumers = copy.copy(callback_queue._consumers)

        correlation_id = str(uuid4())

        future = self.channel.loop.create_future()

        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                body=self.serialize(kwargs),
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=callback_queue.name,
            ),
            routing_key=queue_name,
            mandatory=True
        )

        response = await future

        # Удаление слушателей
        await self.cancel_consumer(callback_queue, consumers)

        return response

    async def consume_queue(self, func, queue_name: str):
        """Регистрация очереди в брокере и получение IncomingMessage в функцию."""
        # Создание queues в рабите
        queue = await self.channel.declare_queue(queue_name)
        await queue.consume(partial(
            self.on_call_message, self.channel.default_exchange, func)
        )

    async def on_call_message(self, exchange, func, message: IncomingMessage):
        payload = self.deserialize(message.body)
        result = await func(**payload)
        result = self.serialize(result)

        await exchange.publish(
            Message(body=result, correlation_id=message.correlation_id),
            routing_key=message.reply_to,
        )
        message.ack()


def connect_data():
    """Данные для подключения к брокеру."""
    return dict(
        login=os.environ.get("RMQ_LOGIN", "user"),
        password=os.environ.get("RMQ_PASSWORD", "bitnami"),
        host=os.environ.get("RMQ_HOST", "127.0.0.1"),
        port=os.environ.get("RMQ_PORT", "5672"),
    )


mq = MessageQueue(**connect_data())
rpc = RPC(**connect_data())
