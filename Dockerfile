FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY webapp/requirements.txt /app/webapp/requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r /app/webapp/requirements.txt
COPY webapp /app/webapp
COPY slk /app/slk
COPY bishop /app/bishop
COPY ctrader /app/ctrader
COPY db /app/db
COPY data /app/data
COPY extension /app/extension
WORKDIR /app/webapp
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
