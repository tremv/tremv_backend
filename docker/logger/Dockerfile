FROM python:3.8.10

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY logger.py .
COPY common.py .
COPY alert.py .
COPY config.json .
COPY alert_config.json .

CMD ["python3", "logger.py"]
