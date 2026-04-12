FROM python:3.11-slim

WORKDIR /app

COPY services/coordinator-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bitable_schema_v12.json ./bitable_schema_v12.json
COPY src ./src
COPY services/coordinator-service/main.py ./main.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/', timeout=3)" || exit 1

CMD ["python", "main.py"]
