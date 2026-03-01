FROM python:3.12-slim

ARG REQUIREMENTS_FILE=requirements/dev.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ${REQUIREMENTS_FILE} /tmp/requirements.txt
COPY requirements/base.txt /tmp/base.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY . /app
