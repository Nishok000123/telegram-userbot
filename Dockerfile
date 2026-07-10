FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

RUN mkdir -p /data/downloads

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose health port for Koyeb Web services (TCP/HTTP check on PORT)
EXPOSE 8000
ENV PORT=8000

CMD ["python", "main.py"]
