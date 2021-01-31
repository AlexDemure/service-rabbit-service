import aio_pika
import requests
import uvicorn
from fastapi import FastAPI
from rabbit.server import mq, rpc, connect_to_broker

app = FastAPI()


@app.on_event('startup')
async def start_message_consuming():
    channel = await connect_to_broker()
    mq.channel = rpc.channel = channel


@app.get("/users")
async def get_users() -> dict:
    """Публичный EndPoint для работы по REST"""
    users = requests.get("https://jsonplaceholder.typicode.com/users")
    return users.json()


@app.get("/mq_send_message")
async def mq_send_message():
    """
    EndPoint для отправки сообщения в сервис B.

    В данном примере используется для удобного тригера отправки сообщения в другой сервис.
    """
    routing_key = "mq_test_queue"  # Название очереди которую слушает сервис B

    # Публикация сообщения.
    await mq.send(routing_key, "hello world")


@app.get("/rpc_send_message")
async def rpc_send_message():
    """
    EndPoint для отправки сообщения в сервис B.

    В данном примере используется для удобного тригера отправки сообщения в другой сервис.
    """
    routing_key = "rpc_test_queue"  # Название очереди которую слушает сервис B

    # Публикация сообщения.

    response = await rpc.call(routing_key)
    return response


if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=7040, reload=True, log_level="debug")
