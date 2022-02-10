FROM python:3.8.10

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt install -y pkg-config
RUN apt install -y libxml2-dev
RUN apt install -y libcurl4-openssl-dev

COPY tremlog_get/ tremlog_get/
WORKDIR tremlog_get/
RUN chmod +x build_lib.sh
RUN ./build_lib.sh
WORKDIR /

COPY config.json .
COPY plot.config .
COPY request.config .
COPY common.py .
COPY server.py .

CMD ["python3", "server.py"]
