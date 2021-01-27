import aio_pika
import requests
import uvicorn
from fastapi import FastAPI
from src.rabbit.server import rabbit

app = FastAPI()


@app.on_event('startup')  # Hook up message consuming to work in same event loop in parallel to Starlette app.
async def start_message_consuming():
    await rabbit.init_connection()


@app.get("/users")
async def get_users() -> dict:
    """Публичный EndPoint для работы по REST"""
    users = requests.get("https://jsonplaceholder.typicode.com/users")
    return users.json()


@app.get("/rpc_send_message")
async def rpc_send_message():
    """
    EndPoint для отправки сообщения в сервис B.

    В данном примере используется для удобного тригера отправки сообщения в другой сервис.
    """
    routing_key = "test_queue"  # Название очереди которую слушает сервис B

    # Публикация сообщения.
    await rabbit.channel.default_exchange.publish(
        aio_pika.Message(b'ServiceA', content_type='text/plain'), routing_key
    )


if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=7040, reload=True, log_level="debug")
