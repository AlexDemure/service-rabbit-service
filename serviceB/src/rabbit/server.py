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

# Параметры RMQ иначе используются дефолтные значения от контейнера.
RMQ_LOGIN = os.environ.get("RMQ_LOGIN", "user")
RMQ_PASSWORD = os.environ.get("RMQ_PASSWORD", "bitnami")
RMQ_HOST = os.environ.get("RMQ_HOST", "127.0.0.1")
RMQ_PORT = os.environ.get("RMQ_PORT", "5672")

# Эти глобальные переменные хранят объекты соединения и канала к брокеру.
# Функция connect_to_broker пытается в первую очередь использовать их, но если их нет, то она создаст их.
BROKER_CONNECTION = None
BROKER_CHANNEL = None


class BaseRMQ:

    channel = None

    def __init__(self, channel: Channel = None):
        self.channel = channel

    @staticmethod
    def serialize(data: Any) -> bytes:
        return json.dumps(data).encode()

    @staticmethod
    def deserialize(data: bytes) -> Any:
        return json.loads(data)


class MessageQueue(BaseRMQ):
    """Класс предазначен для работы по принципу publisher / subscriber."""

    async def send(self, queue_name: str, data: Any):
        """MQ-метод для отправки месседжа в один конец."""
        # Крафт месседджа.
        # Месседж - объект который получит другой сервис.
        message = Message(
            body=self.serialize(data),
            content_type="application/json",
            correlation_id=str(uuid4()),
        )
        # Публикация сообщения в брокер используя дефолтную очередь.
        await self.channel.default_exchange.publish(message, queue_name)

    async def consume_queue(self, func, queue_name: str, auto_delete_queue: bool = False):
        """Прослушивание очереди брокера."""
        # Создание queues в рабите
        queue = await self.channel.declare_queue(queue_name, auto_delete=auto_delete_queue, durable=True)

        # Вроде как постоянное итерирование по очереди в ожидании месседжа.
        # Есть алтернативный вариант получения месседжа через queue.get(timeout=N)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                logging.debug(f'Received message body: {message.body}')
                await func(message)


class RPC(BaseRMQ):
    """Класс предазначен для работы по принципу удаленных вызовов (RPC)."""

    futures = {}

    @staticmethod
    async def cancel_consumer(queue, consumers):
        """
        Удаление из очереди слушателей

        Необходимо для того чтобы убрать привязанного слушателя от очереди после получения сообщения.
        На работу системы никак не влияет необходимо лишь для того что подчищать очереди из брокера.
        """
        for key, val in consumers.items():
            await queue.cancel(key)

    def on_response(self, message: IncomingMessage):
        """
        Функция которая обрабатывает приходящий ответ из другого сервиса

        Magic-method
        """
        future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)
        message.ack()

    async def call(self, queue_name: str, **kwargs):
        """
        RPC-метод для отправки в другой сервис с целью возврата ответа из другого сервиса.

        Данный метод на каждый вызов создает уникальную очередь
        тем самым не скапливая в одной очереди множество запросов.

        Важно!!! Узнать в лучший способ использования создания анонимных очередей.
        """
        # Создание уникальной очереди на которую будет возвращен ответ из другого сервиса.
        callback_queue = await self.channel.declare_queue(exclusive=True, auto_delete=True, durable=True)

        await callback_queue.consume(self.on_response)  # Метод класса который обрабатывает ответ

        consumers = copy.copy(callback_queue._consumers)  # Копирование консумеров для удаления очереди из раббита

        correlation_id = str(uuid4())

        # Magic #1
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

        # Magic #2 Выполняется только после того как другой сервис пришлет запрос.
        response = await future

        # Magic #3 Удаление слушателей.
        # Почему-то даже с auto_delete очередь после выполнения не удаляется ссылаясь на консумера.
        # Поэтому решение было вручную удалять консумера после выполнения задачи.
        await self.cancel_consumer(callback_queue, consumers)

        return self.deserialize(response)

    async def consume_queue(self, func, queue_name: str):
        """Прослушивание очереди брокера."""
        queue = await self.channel.declare_queue(queue_name)

        # Все очереди обрабатываются одной общей функцией.
        # В нее передается exchange, func и сам message.

        # Exchange используется для возврата ответа используя метод publish.

        # partial работает как генерировании функции с аргументами,
        # Если пройтись по стеку тогда там на выходе будет что-то подобного on_call_message(message, exchange, func)
        await queue.consume(partial(
            self.on_call_message, self.channel.default_exchange, func)
        )

    async def on_call_message(self, exchange, func, message: IncomingMessage):
        """Единая функция для приема message из других сервисов и отправки обратно ответа."""
        payload = self.deserialize(message.body)
        try:
            result = await func(**payload)
        except Exception as e:
            result = self.serialize(dict(error='error', reason=str(e)))

        result = self.serialize(result)

        await exchange.publish(
            Message(body=result, correlation_id=message.correlation_id),
            routing_key=message.reply_to,
        )
        message.ack()


async def connect_to_broker() -> Channel:
    """Подключение к брокеру и возвращат канал для работы с брокером."""
    global BROKER_CONNECTION
    global BROKER_CHANNEL

    retries = 0
    while not BROKER_CONNECTION:
        conn_str = f"amqp://{RMQ_LOGIN}:{RMQ_PASSWORD}@{RMQ_HOST}:{RMQ_PORT}/"
        print(f"Trying to create connection to broker: {conn_str}")
        try:
            BROKER_CONNECTION = await aio_pika.connect_robust(conn_str)
            print(f"Connected to broker ({type(BROKER_CONNECTION)} ID {id(BROKER_CONNECTION)})")
        except Exception as e:
            retries += 1
            print(f"Can't connect to broker {retries} time({e.__class__.__name__}:{e}). Will retry in 5 seconds...")
            sleep(5)

    if not BROKER_CHANNEL:
        print("Trying to create channel to broker")
        BROKER_CHANNEL = await BROKER_CONNECTION.channel()
        print("Got a channel to broker")

    return BROKER_CHANNEL


mq = MessageQueue()
rpc = RPC()
