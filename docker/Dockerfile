FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bitable_schema_v12.json ./bitable_schema_v12.json
COPY src/ ./src/
COPY services/coordinator-service/main.py ./main.py

EXPOSE 8003

CMD ["python", "main.py"]
