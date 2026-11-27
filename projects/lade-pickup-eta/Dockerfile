# API image. Build after training so artifacts/bundle.joblib exists:
#   python -m lade_eta train && docker build -t lade-pickup-eta .
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

# LightGBM needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY lade_eta/ lade_eta/
COPY artifacts/bundle.joblib artifacts/bundle.joblib

ENV LADE_ARTIFACT_DIR=/app/artifacts PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
USER nobody
CMD ["python", "-m", "lade_eta", "serve", "--port", "8000"]
