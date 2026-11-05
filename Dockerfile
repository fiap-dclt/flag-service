# ==========================================
# Stage 1: Build
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instalar dependências de sistema para compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Limpeza extrema do VENV
RUN pip uninstall -y pip wheel \
    && find /opt/venv -type d -name "__pycache__" -exec rm -r {} + \
    && find /opt/venv -name "*.pyc" -delete

# ==========================================
# Stage 2: Imagem Final Distroless
# ==========================================
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copia apenas o venv limpo
COPY --from=builder --chown=nonroot:nonroot /opt/venv /opt/venv

ENV PYTHONPATH="/opt/venv/lib/python3.11/site-packages"
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=nonroot:nonroot ./app.py .

USER nonroot

EXPOSE 8002

# Distroless exige invocação direta do binário
CMD ["/opt/venv/bin/gunicorn", "--bind", "0.0.0.0:8002", "app:app"]