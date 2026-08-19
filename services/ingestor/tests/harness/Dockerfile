# syntax=docker/dockerfile:1.4
FROM dhi.io/python:3.14-debian13@sha256:aa0ca597178dc1f272f15ed23a213becab317bd8c47af82694a497a51dc8cee6

WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

COPY services/ingestor/tests/harness/test_harness_server.py /app/server.py

USER appuser

EXPOSE 8080
CMD ["python", "/app/server.py"]
