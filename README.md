
## Развертывание микросервисов на FastAPI с применением RabbitMQ
##### Данный пример не использует Celery, Redis, Celery-flower

### Технологии:
- FastAPI
- RabbitMQ(aiopika)
- Docker
- Docker-compose

#### О сервисах
- СервисА (Отправитель) 
- СервисБ (Слушатель)
- Rabbit (Брокер сообщений)

Также каждый из сервисов поддерживает RESTApi за счет FastApi.
Поэтому каждое из наших сервисов имеет два типа общения RPC и REST тем самым разграничивая приватные и публичные методы системы.
### Развертывание
```sh
docker-compose up -d --build
```

#### Статус СервисаА
```sh
INFO:     Uvicorn running on http://127.0.0.1:7040 (Press CTRL+C to quit)
INFO:     Started reloader process [1]
INFO:     Started server process [8]
INFO:     Waiting for application startup.
DEBUG:    Creating AMQP channel for connection: <RobustConnection: "amqp://user:******@127.0.0.1:5672/" 0 channels>
DEBUG:    Channel created: <RobustChannel "None#Not initialized channel">
INFO:     Application startup complete.
Connection to RabbitMQ
```

#### Статус СервисаБ
```sh
INFO:     Uvicorn running on http://127.0.0.1:7041 (Press CTRL+C to quit)
INFO:     Started reloader process [1]
INFO:     Started server process [8]
INFO:     Waiting for application startup.
DEBUG:    Creating AMQP channel for connection: <RobustConnection: "amqp://user:******@127.0.0.1:5672/" 0 channels>
DEBUG:    Channel created: <RobustChannel "None#Not initialized channel">
DEBUG:    Declaring queue: <Queue(test_queue): auto_delete=False, durable=None, exclusive=False, arguments=None>
INFO:     Application startup complete.
```

### Немного о коде
####  RabbitMQ - Submodule
Каждый из сервисов должен иметь коннект к брокеру
 но в некоторых практиках не всегда отдельный сервис находится в одном репозитории
 поэтому в таких случаях лучше сделать код с rabbit отдельным репозиторием и шарить между сервисами.
В примере для простоты развертывания был продублирован код из одного сервиса в другой для наглядности.

#### Подключение коннекта сервиса к брокеру
В каждом сервисе есть файл src/rabbit/server.py там находится класс RabbitMQ с методами для работы с брокером. <br>
Для того чтобы подключится к брокеру в каждом сервисе необходимо перед запуском приложения сделать:
```sh
from scr.rabbit.server import rabbit

await rabbit.init_connection()
```
rabbit - Инстанс класса RabbitMQ в котором устанавливаются параметры к брокеру (логин, пароль, хост, пароль) <br>

В случае с использованием FastAPI есть startup events можно сделать таким образом:
```sh
@app.on_event('startup')
async def start_message_consuming():
    await rabbit.init_connection()  # Инициализация коннекта и создание channel
```

#### Регистрация слушателей очередей (СервисБ)
Если ваш сервис будет принимать сообщения тогда необходимо зарегестировать функции которые будут слушать очереди тем самым получая сообщения из брокера. <br>
Сделать это можно таким способом: <br>
Первым аргументом принимает coro-функция вторым название очереди в брокере
```sh
all_consumers = (
    rabbit.consume_queue(rpc_accept_message, "test_queue"),
)

```
Для того чтобы сервер начал слушать очереди необходимо расширить startup events.
```sh
@app.on_event('startup')
async def start_message_consuming():
    await rabbit.init_connection()  # Инициализация коннекта и создание channel
    asyncio.ensure_future(asyncio.gather(*all_consumers), loop=asyncio.get_event_loop())
```
С данной манипуляцией ваши очереди будут крутиться параллельно с вашим FastApi приложением.

#### Публикация сообщений в брокер (СервисА)
Для начала сделайте предыдущие шаги описывающие инициализацию и подключение к брокеру. <br>
Для отправки сообщения в брокер необходимо:
```sh
routin_key = "test_queue" (может быть любое название)
await rabbit.channel.default_exchange.publish(
    aio_pika.Message(b'ServiceA', content_type='text/plain'), routing_key
)
```

#### Результат приема сообщения из сервисаА
```sh
DEBUG:    Received message body: b'ServiceA'
DEBUG:    b'ServiceA'
```
### Админ панель RabbitMQ
Для того чтобы зайти в админ.панель брокера необходимо перейти по адресу:
```sh
http://localhost:15672/
LOGIN=user
PASSWORD=bitnami
```

### Принцип работы сервисов
![alt text](https://habrastorage.org/webt/yr/6u/5v/yr6u5v6ebof-6gahbxtyj_fspo8.png)