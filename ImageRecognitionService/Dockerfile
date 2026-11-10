# The Detection Service, run by WebApp/docker-compose.yml (profile "app") on
# the range PC: its Python, PyTorch and OpenCV come with the image rather than
# installed on Windows, Docker restarts it when it stops, and `docker stop`
# sends the SIGTERM on which it ends its Run and posts what it holds.
FROM python:3.14-slim

# OpenCV's runtime libraries; tzdata so TZ (the PC's zone) applies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /service

# PyTorch for the CPU, unless built for an NVIDIA GPU:
#   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu126 (docker-compose.gpu.yml)
# installed first, so ultralytics finds it rather than PyPI's CUDA build
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url "$TORCH_INDEX" \
  && pip install --no-cache-dir -r requirements.txt

COPY detection detection
# detection imports tools.manifest
COPY tools tools
COPY trained_models trained_models
COPY config config
COPY data/targets data/targets

# The range PC is offline: ultralytics checks nothing online
ENV YOLO_OFFLINE=1 PYTHONUNBUFFERED=1

EXPOSE 8010
CMD ["python", "-m", "detection.service", "--host", "0.0.0.0", "--log-dir", "/var/log/kanat"]
