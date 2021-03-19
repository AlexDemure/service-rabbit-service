import logging

import requests
import uvicorn
from fastapi import FastAPI
from rabbit.server import mq, rpc, connect_to_broker

app = FastAPI()


@app.on_event('startup')
async def start_message_consuming():
    channel = await connect_to_broker()
    mq.channel = rpc.channel = channel

    await rpc.consume_queue(rpc_accept_message, "rpc_test_queue")
    await mq.consume_queue(mq_accept_message, "mq_test_queue")


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
    print(get_fake_data())
    # test = 1 / 0
    # Если не ack-ать message тогда она будет висеть в рабите
    # и при перезапуске приложения этот message снова попадет в функцию.
    await msg.ack()


async def rpc_accept_message(**kwargs):
    print(**kwargs)
    return get_fake_data()


if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=7041, reload=True, log_level="debug")
