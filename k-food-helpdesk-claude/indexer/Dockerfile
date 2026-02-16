FROM python:3.11-slim
WORKDIR /app
COPY server/requirements.txt /app/server_requirements.txt
COPY indexer/requirements.txt /app/indexer_requirements.txt
RUN pip install --no-cache-dir -r /app/server_requirements.txt -r /app/indexer_requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1
