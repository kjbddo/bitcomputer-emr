FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/AI_BackEnd

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/AI_BackEnd/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/AI_BackEnd
RUN mkdir -p /app/Back-End/BitComputer/images

EXPOSE 5000
CMD ["python", "app.py"]
