# syntax=docker/dockerfile:1.4
FROM dhi.io/python:3.14-debian13-dev@sha256:1977c4a9624171ef582e641eb6f67adfc3f4b3ec0cb59345876f1928cda6f698

WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

COPY services/ingestor/tests/harness/test_harness_server.py /app/server.py

USER 65532

EXPOSE 8080
CMD ["python", "/app/server.py"]
