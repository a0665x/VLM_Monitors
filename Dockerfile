FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    curl \
    ffmpeg \
    libavdevice-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    pkg-config \
    libportaudio2 \
    alsa-utils \
    pulseaudio-utils \
    v4l-utils \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
COPY temp/mediamtx ./temp/mediamtx
RUN chmod +x ./temp/mediamtx

# Expose ports
# 5000: Flask Web Server
# 8554: RTSP (if running in same container, but we use host net)
# 8888: HLS (MediaMTX)
EXPOSE 5000

# Run the application
CMD ["python", "src/server.py"]
