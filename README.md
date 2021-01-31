
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

##### Важно
___
Данное руководство не подходит для боевоего режима т.к требует доп. обработок исключений и доп. знаний работы с брокером.
___
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
INFO:     Started server process [9]
INFO:     Waiting for application startup.
DEBUG:    Creating AMQP channel for connection: <RobustConnection: "amqp://user:******@127.0.0.1:5672/" 0 channels>
DEBUG:    Channel created: <RobustChannel "None#Not initialized channel">
DEBUG:    Declaring queue: <Queue(rpc_test_queue): auto_delete=False, durable=None, exclusive=False, arguments=None>
DEBUG:    Start to consuming queue: <Queue(rpc_test_queue): auto_delete=False, durable=None, exclusive=False, arguments=None>
DEBUG:    Declaring queue: <Queue(mq_test_queue): auto_delete=False, durable=True, exclusive=False, arguments=None>
DEBUG:    Start to consuming queue: <Queue(mq_test_queue): auto_delete=False, durable=True, exclusive=False, arguments=None>
```

### Немного о коде
####  RabbitMQ - Submodule
Каждый из сервисов должен иметь коннект к брокеру
 но в некоторых практиках не всегда отдельный сервис находится в одном репозитории
 поэтому в таких случаях лучше сделать код с rabbit отдельным репозиторием и шарить между сервисами.
В примере для простоты развертывания был продублирован код из одного сервиса в другой для наглядности.

#### Подключение коннекта сервиса к брокеру
В каждом сервисе есть файл src/rabbit/server.py там находится класс RQ и RPC с методами для работы с брокером. <br>
Для того чтобы подключится к брокеру в каждом сервисе необходимо перед запуском приложения сделать:
```sh
from scr.rabbit.server import rpc, mq, connect_to_broker

channel = await connect_to_broker()
rpc.channel = mq.channel = channel
```
rabbit - Инстанс класса RabbitMQ в котором устанавливаются параметры к брокеру (логин, пароль, хост, пароль) <br>

В случае с использованием FastAPI есть startup events можно сделать таким образом:
```sh
@app.on_event('startup')
async def start_message_consuming():
    channel = await connect_to_broker()
    rpc.channel = mq.channel = channel
```

#### Регистрация слушателей очередей (СервисБ)
Если ваш сервис будет принимать сообщения тогда необходимо зарегестировать функции которые будут слушать очереди тем самым получая сообщения из брокера. <br>
Сделать это можно таким способом: <br>
Первым аргументом принимает функцию вторым название очереди в брокере
```sh
@app.on_event('startup')
async def start_message_consuming():
    ....

    await rpc.consume_queue(rpc_accept_message, "rpc_test_queue")
    await mq.consume_queue(mq_accept_message, "mq_test_queue")

```

####  Публикация сообщений в брокер (СервисА)
##### MessageQueue
```sh
routing_key = "mq_test_queue"  # Название очереди которую слушает сервис B

# Публикация сообщения.
await mq.send(routing_key, "hello world")
```
##### RPC
```sh
routing_key = "rpc_test_queue"  # Название очереди которую слушает сервис B

# Публикация сообщения.
response = await rpc.call(routing_key)
```

### Админ панель RabbitMQ
Для того чтобы зайти в админ.панель брокера необходимо перейти по адресу:
```sh
http://localhost:15672/
LOGIN=user
PASSWORD=bitnami
```

### Принцип работы сервисов
![alt text](https://habrastorage.org/webt/pu/1n/o0/pu1no0iay2kvznpkpgzjy-f5afy.png)