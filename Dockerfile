FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY  requirements.txt .

RUN pip install --no-cache-dir  -r requirements.txt  && \
    rm requirements.txt

COPY chat .

EXPOSE 8000
CMD ["uvicorn", "chat.main:app", "--host", "0.0.0.0", "--port", "8000"]
#uvicorn main:chat --host 0.0.0.0 --port 8000
#uvicorn chat.main:app --host 0.0.0.0 --port 8000 --reload