FROM tiangolo/uvicorn-gunicorn:python3.8

RUN pip install aio-pika fastapi requests

COPY . .

EXPOSE 7041

CMD ["python", "src/main.py"]