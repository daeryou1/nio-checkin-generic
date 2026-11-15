FROM python:3.12-alpine

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    RUN_ON_START=1

WORKDIR /app
COPY checkin.py /app/checkin.py
COPY server.py /app/server.py
RUN mkdir -p /app/data

# 零第三方依赖, 无需 pip install。
# CMD 默认跑签到常驻; 需要 Web 配置页时用 docker compose --profile web up -d
CMD ["python", "-u", "/app/checkin.py"]
