# Imagen de la API de valoración (FastAPI → Render).
#
# Multi-stage: `builder` instala las dependencias runtime desde pyproject.toml
# (versiones pinnadas) en un prefijo aislado; `runtime` copia solo ese prefijo
# más el código de la app. No se incluyen las herramientas de dev.
#
# La app (`api/main.py`) aún está en desarrollo; el WORKDIR queda listo para
# cuando ese módulo exista (README.md:221 lo documenta como `uvicorn api.main:app`).
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY api ./api

RUN pip install --prefix=/install .


FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /app/src ./src
COPY --from=builder /app/api ./api

# Esqueleto de la raíz (directorios que los módulos crean bajo data/models).
RUN mkdir -p /app/data/raw /app/data/processed /app/models

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]