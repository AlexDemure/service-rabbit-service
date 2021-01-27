import asyncio
import logging
import os

import aio_pika


class RabbitMQ:

    HOST: str = None
    PORT: str = None
    login: str = None
    password: str = None

    url_connection: str = None
    connection = None
    channel = None

    def __init__(self, login: str, password: str, host: str = "127.0.0.1", port: str = "5672"):
        self.login = login
        self.password = password
        self.HOST = host
        self.PORT = port

        self.url_connection = self.get_url_connection()

    def get_url_connection(self) -> str:
        """Генерирование ULR-строки к брокеру."""
        return f"amqp://{self.login}:{self.password}@{self.HOST}:{self.PORT}/"

    async def init_connection(self):
        """Инициализация коннекта к брокеру"""
        tries = 0
        while True:
            try:
                print("Connection to RabbitMQ")
                self.connection = await aio_pika.connect_robust(self.url_connection)
                break
            except Exception as e:
                if tries > 5:
                    raise Exception

                print(f"Connection failed reason: {e}")
                print(f"Try#{tries+1} | Waiting 5 seconds to retry....")
                tries += 1
                await asyncio.sleep(5)

        self.channel = await self.connection.channel()

    async def consume_queue(self, func, queue_name: str, auto_delete_queue: bool = False):
        """Регистрация очереди в брокере и получение IncomingMessage в функцию."""
        queue = await self.channel.declare_queue(queue_name, auto_delete=auto_delete_queue)  # Создание queues в рабите
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                logging.debug(f'Received message body: {message.body}')

                # TODO Сделать передачу функции как сихнронной так и асихнронной.
                await func(message)


rabbit = RabbitMQ(
    login=os.environ.get("RMQ_LOGIN", "user"),
    password=os.environ.get("RMQ_PASSWORD", "bitnami")
)
