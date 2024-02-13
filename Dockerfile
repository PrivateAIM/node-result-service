FROM python:3.11-alpine AS builder

WORKDIR /tmp
COPY ./pyproject.toml ./poetry.lock ./

RUN pip install poetry==1.7.1 && \
    poetry export -n --without dev -f requirements.txt -o requirements.txt

FROM python:3.11-alpine

WORKDIR /app

COPY ./config/ ./config/
COPY --from=builder /tmp/requirements.txt ./
COPY ./project/ ./project/

RUN pip install -r requirements.txt

# PYTHONPATH hack is needed here because /app contains the "project"
# module which is referenced in parts of the source code.
ENV PYTHONPATH=/app

CMD ["python", "project/main.py", "server", "--no-reload", "-p", "8080"]
