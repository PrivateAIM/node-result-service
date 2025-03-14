# python:3.13-alpine3.21
FROM python@sha256:323a717dc4a010fee21e3f1aac738ee10bb485de4e7593ce242b36ee48d6b352 AS builder

WORKDIR /tmp
COPY ./pyproject.toml ./poetry.lock ./

RUN set -ex && \
        python -m pip install --disable-pip-version-check --no-cache-dir poetry==2.1.0 && \
        poetry self add poetry-plugin-export==1.9.0 && \
        poetry export -n -f requirements.txt -o requirements.txt

FROM python@sha256:323a717dc4a010fee21e3f1aac738ee10bb485de4e7593ce242b36ee48d6b352

LABEL org.opencontainers.image.source=https://github.com/PrivateAIM/node-result-service
LABEL org.opencontainers.image.description="Service that handles result files for federated analyses within FLAME."
LABEL org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app

COPY ./config/ ./config/
COPY --from=builder /tmp/requirements.txt ./
COPY pyproject.toml README.md ./
COPY ./project/ ./project/
COPY ./docker-entrypoint.sh ./

RUN set -ex && \
        addgroup nonroot && \
        adduser nonroot -G nonroot -s /bin/sh -D && \
        chown -R nonroot:nonroot /app

RUN set -ex && \
      python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt

# PYTHONPATH hack is needed here because /app contains the "project"
# module which is referenced in parts of the source code.
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT [ "/app/docker-entrypoint.sh" ]
CMD [ "--host", "0.0.0.0", "--port", "8080", "--workers", "4" ]
