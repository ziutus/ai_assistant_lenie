FROM postgres:18-bookworm

LABEL maintainer="Krzysztof Józwiak <krzysztof@lenie-ai.eu>"

COPY backend/database/init/* /docker-entrypoint-initdb.d

RUN apt-get update \
  && apt-cache search postgresql-18- \
  && apt-get install -y --no-install-recommends postgresql-18-pgvector \
  && rm -rf /var/lib/apt/lists/*
