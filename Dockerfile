FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/comfyflow/ src/comfyflow/
COPY config/ config/
COPY workflows/ workflows/

ENV COMFYUI_URL=http://localhost:8188

CMD ["python", "-m", "comfyflow.panel"]
