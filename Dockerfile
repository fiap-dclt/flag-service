
# ==========================================
# Stage 1: Build das dependências Python
# ==========================================
# Utiliza Python 3.13 e Debian 13, compatíveis com a imagem Distroless final.
FROM python:3.13-slim-trixie AS builder

WORKDIR /app

# Cria um ambiente virtual isolado para as dependências da aplicação.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# O compilador é utilizado somente no estágio de build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala as dependências do Flag Service.
RUN python -m pip install --no-cache-dir -r requirements.txt

# Mantém o setuptools para compatibilidade com outras bibliotecas.
# Atualiza suas dependências internas para corrigir vulnerabilidades.
RUN python -m pip install --no-cache-dir --upgrade setuptools==80.10.2

# Verifica a consistência das dependências instaladas.
# Valida também o driver PostgreSQL e o cliente HTTP.
RUN python -m pip check \
    && python -c "import flask, gunicorn, psycopg2, requests, dotenv, setuptools; print('Dependencies OK')"

# Remove somente o pip após a instalação e validação.
# Preserva setuptools e todas as dependências da aplicação.
RUN python -m pip uninstall -y pip \
    && find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name "*.pyc" -delete

# ==========================================
# Stage 2: Imagem final Distroless
# ==========================================
# Utiliza Debian 13 e usuário não privilegiado.
FROM gcr.io/distroless/python3-debian13:nonroot

WORKDIR /app

# Copia o ambiente virtual com as dependências já instaladas.
COPY --from=builder --chown=nonroot:nonroot /opt/venv /opt/venv

# Configura os caminhos para o interpretador Python 3.13.
ENV PYTHONPATH="/opt/venv/lib/python3.13/site-packages"
ENV PATH="/opt/venv/bin:$PATH"

# Copia somente o código da aplicação.
COPY --chown=nonroot:nonroot app.py .

USER nonroot

EXPOSE 8002

# Inicia o Gunicorn utilizando o Python da imagem Distroless.
# Mantém a porta 8002 acessível dentro do Kubernetes.
ENTRYPOINT ["/usr/bin/python", "-m", "gunicorn"]
CMD ["--bind", "0.0.0.0:8002", "app:app"]
