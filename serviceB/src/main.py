import asyncio
import logging

import requests
import uvicorn
from fastapi import FastAPI
from src.rabbit.server import rabbit

app = FastAPI()


@app.on_event('startup')  # Hook up message consuming to work in same event loop in parallel to Starlette app.
async def start_message_consuming():
    await rabbit.init_connection()  # Инициализация коннекта и создание channel
    asyncio.ensure_future(asyncio.gather(*all_consumers), loop=asyncio.get_event_loop())


def get_fake_data() -> dict:
    """Открытый API-endpoint для получение рандомных данных."""
    posts = requests.get("https://jsonplaceholder.typicode.com/posts")
    return posts.json()


@app.get("/posts")
async def get_posts() -> dict:
    """Публичный EndPoint для работы по REST"""
    return get_fake_data()


async def mq_accept_message(msg) -> None:
    """MQ-функция которая слушает очередь test-queue приходит объект IncomingMessage"""
    logging.debug(f"{msg.body}")

    # По дефолту в rabbit.server.py автоматическое удаление сообщения поставлено в положение False
    # для того чтобы контролировать когда сообщение будет выполнено полностью лучше использовать в конце функции.
    # Если не ack-ать message тогда она будет висеть в рабите и при перезапуске приложения этот message снова попадет в функцию.
    await msg.ack()


# Регистрация слушателей очереди.
# Для этого необходимо передать пока что функцию (коротину) и название очереди которую будет слушать эта функция.
all_consumers = (
    rabbit.consume_queue(mq_accept_message, "mq_test_queue"),
)


if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=7041, reload=True, log_level="debug")
