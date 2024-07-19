FROM python:3.12-alpine AS builder

WORKDIR /tmp
COPY ./pyproject.toml ./poetry.lock ./

RUN set -ex && \
        python -m pip install --disable-pip-version-check --no-cache-dir poetry==1.8.3 && \
        poetry self add poetry-plugin-export && \
        poetry export -n -f requirements.txt -o requirements.txt

FROM python:3.12-alpine

WORKDIR /app

COPY ./config/ ./config/
COPY --from=builder /tmp/requirements.txt ./
COPY pyproject.toml README.md ./
COPY ./project/ ./project/

RUN set -ex && \
        addgroup -S nonroot && \
        adduser -S nonroot -G nonroot && \
        chown -R nonroot:nonroot /app

RUN set -ex && \
      python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt

# PYTHONPATH hack is needed here because /app contains the "project"
# module which is referenced in parts of the source code.
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT [ "/usr/local/bin/python", "-m", "uvicorn", "project.server:app" ]
CMD [ "--host", "0.0.0.0", "--port", "8080", "--workers", "4" ]

USER nonroot
