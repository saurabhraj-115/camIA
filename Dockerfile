FROM python:3.11-slim

# System libs required by OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libglx-mesa0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p snapshots configs static

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6789

ENTRYPOINT ["/entrypoint.sh"]
