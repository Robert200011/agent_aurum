FROM python:3.12-slim AS runtime

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.source="aurum-agent" \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.created=$BUILD_DATE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system aurum && adduser --system --ingroup aurum aurum

COPY pyproject.toml ./
COPY project_introduction/README.md ./project_introduction/README.md
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

RUN pip install --upgrade pip "setuptools>=78.1.1" && pip install .

USER aurum
EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
