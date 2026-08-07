FROM python:3.14-slim

WORKDIR /app
COPY services/ingestor/tests/harness/test_harness_server.py /app/server.py

EXPOSE 8080
CMD ["python", "/app/server.py"]
