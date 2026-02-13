# Production Dockerfile for Wave OS
# Build: docker build -t waveos:latest .
# Run:  docker run --rm waveos run --in /data/run --baseline /data/baseline --out /data/out

FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir build \
  && python -m build --wheel \
  && pip wheel --no-deps --wheel-dir /wheels dist/*.whl

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV WAVEOS_LOG_FORMAT=json

# Non-root user for production
RUN addgroup --system waveos && adduser --system --ingroup waveos waveos

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
  && rm -rf /wheels \
  && mkdir -p /data /app/out \
  && chown -R waveos:waveos /app /data

USER waveos

# Default: show help. Override with run/sim/baseline/etc.
ENTRYPOINT ["waveos"]
CMD ["--help"]
