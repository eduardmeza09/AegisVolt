# Imagen única parametrizada: docker build --build-arg SERVICE=<paquete> services/
# Paquetes: station_reservation_service | billing_wallet_service | energy_dispatch_service | graphql_gateway
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml .
RUN python -c "import tomllib;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > req.txt \
 && pip install --prefix=/install -r req.txt

FROM python:3.12-slim
ARG SERVICE
ARG APP_VERSION=dev
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app:/app/libs \
    SERVICE_MODULE=${SERVICE} APP_VERSION=${APP_VERSION}
COPY --from=builder /install /usr/local
WORKDIR /app
COPY libs/ ./libs/
COPY ${SERVICE}/ ./${SERVICE}/
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn ${SERVICE_MODULE}.main:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log"]
