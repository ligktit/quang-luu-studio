FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Tạo bảng (idempotent) rồi chạy gunicorn + uvicorn workers.
#
# --forwarded-allow-ips='*': BẮT BUỘC. Container chỉ publish trên 127.0.0.1 của
# host (docker-compose.yml) nên chỉ Nginx tới được — không ai bơm X-Forwarded-For
# giả từ ngoài vào. Thiếu cờ này thì peer là gateway bridge của Docker (172.x.0.1),
# không khớp mặc định "127.0.0.1", nên uvicorn bỏ qua X-Forwarded-For và
# get_remote_address() trả CÙNG MỘT IP cho mọi khách hàng → rate-limit biến thành
# hạn mức dùng chung cho cả hệ thống → 429 hàng loạt.
CMD ["sh", "-c", "python -m app.cli init-db && gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 --forwarded-allow-ips='*'"]
