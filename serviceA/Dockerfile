FROM tiangolo/uvicorn-gunicorn:python3.8

RUN pip install aio-pika fastapi requests

COPY src ./src/

EXPOSE 7040

CMD ["python", "src/main.py"]