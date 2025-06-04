FROM python:3.12.10-slim

RUN pip install fastapi uvicorn kubernetes
WORKDIR /app

RUN apt update && \
  apt install -y curl && \
  curl -LO "https://dl.k8s.io/release/v1.33.1/bin/linux/amd64/kubectl" && \
  chmod +x kubectl
