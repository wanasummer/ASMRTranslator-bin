ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG ENGINE_EXTRA=engine-gpu
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONUNBUFFERED=1 \
    CHICKENRICE_RUNTIME_DIR=/data \
    CHICKENRICE_HOST=0.0.0.0 \
    CHICKENRICE_PORT=7870 \
    CHICKENRICE_DEVICE=cuda \
    CHICKENRICE_COMPUTE_TYPE=int8_float16

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3.10-venv python3-pip ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/chickenrice-service
COPY pyproject.toml ./
COPY src ./src
RUN python3.10 -m pip install --no-cache-dir ".[${ENGINE_EXTRA}]"
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 7870
ENTRYPOINT ["./docker-entrypoint.sh"]
