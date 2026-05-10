# VLM_Monitors - Project Overview

## 📋 Project Summary

**VLM_Monitors** is an AI-powered, real-time video monitoring system designed for NVIDIA Jetson devices (Orin Nano/AGX). It combines **live video streaming**, **local AI inference**, and **intelligent risk detection** with a privacy-first approach—all video processing happens on-device using Ollama models.

### Core Capabilities
- 🎥 **Real-Time Video Streaming**: Low-latency RTSP/HLS streaming via MediaMTX
- 🤖 **AI-Powered Risk Detection**: Vision Language Models (VLM) analyze frames for safety risks
- 💬 **Interactive Chat Agent**: Multi-provider LLM chat with tool calling (Gemini/Groq/Ollama)
- 📱 **Smart Alerts**: Twilio SMS + Webhook notifications with cooldown and thresholds
- 🔒 **Privacy-First**: All inference runs locally, video never leaves the device
- 📊 **System Monitoring**: Real-time CPU/RAM/GPU metrics

---

## 🏗️ System Architecture

### Technology Stack
- **Platform**: NVIDIA Jetson Orin Nano/AGX (ARM64, CUDA)
- **Language**: Python 3.10+ with Flask/Socket.IO backend
- **Frontend**: HTML/CSS/JavaScript with HLS.js for video playback
- **Video Pipeline**: GStreamer → FFmpeg → MediaMTX → RTSP/HLS
- **AI/ML**: Ollama (local LLM/VLM), supports Gemini and Groq APIs
- **Containerization**: Docker with NVIDIA runtime support

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface                            │
│  http://localhost:5000 (Flask + Socket.IO + HLS.js)             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ├─→ WebSocket (Real-time metrics, status)
                       └─→ HLS Stream (http://localhost:8888/camera)
                       
┌─────────────────────────────────────────────────────────────────┐
│                     Flask Backend Server                         │
│  - CameraThread: Captures frames, manages RTSP publishing       │
│  - AnalysisThread: Periodic VLM risk analysis                   │
│  - Socket.IO: Real-time communication                           │
└──────────────┬───────────────┬──────────────┬───────────────────┘
               │               │              │
               ▼               ▼              ▼
       ┌──────────────┬────────────────┬─────────────┐
       │ GStreamer    │  MediaMTX      │  Ollama     │
       │ v4l2src      │  RTSP/HLS      │  VLM API    │
       │ nvv4l2h264enc│  :8554/:8888   │  :11434     │
       └──────────────┴────────────────┴─────────────┘
```

### Video Capture Pipeline (Optimized for Low Latency)

```
/dev/video0 (USB Camera)
    │
    ▼
[GStreamer Pipeline]
 ├─ v4l2src: Hardware video capture at 30 FPS
 ├─ queue (max-size-buffers=1, leaky=downstream): Drop old frames
 ├─ videoconvert: Convert to BGR format
 └─ fdsink: Pipe raw frames to Python
    │
    ▼
[CameraThread - Python]
 ├─ Read frames from GStreamer stdout
 ├─ Apply risk overlay (if detected)
 ├─ Encode to H.264 via nvv4l2h264enc (NVIDIA GPU)
 └─ Pipe to FFmpeg for RTSP publishing
    │
    ▼
[FFmpeg RTSP Publisher]
 ├─ Read H.264 stream from stdin
 ├─ Publish to rtsp://localhost:8554/camera
 └─ Flags: -flags low_delay, -fflags nobuffer (minimal latency)
    │
    ▼
[MediaMTX Server]
 ├─ RTSP Endpoint: rtsp://127.0.0.1:8554/camera
 ├─ HLS Endpoint: http://localhost:8888/camera/index.m3u8
 └─ Config: hlsAlwaysRemux: yes, hlsSegmentDuration: 1s
    │
    ▼
[Frontend - HLS.js Player]
 ├─ Aggressive buffering (1s max buffer vs default 30s)
 ├─ Live-edge sync (0.5s from live)
 └─ Result: <2s end-to-end latency
```

**Latency Breakdown** (Optimized):
- Camera Capture: ~33ms (30 FPS)
- Encoding: ~10ms (NVIDIA H.264 hardware encoder)
- RTSP Transport: ~50ms
- HLS Segmentation: ~1000ms (1s segments)
- Client Buffer: ~500ms (0.5s live-edge sync)
- **Total: ~1.6s** (down from ~3s before optimization)

---

## 🎯 Core Features

### 1. Risk Detection Mode
**Continuous monitoring with AI-powered risk analysis**

- **Customizable Risk Prompts**: Define safety criteria with prompt history
- **Auto/Manual Analysis**: Interval-based automatic analysis + on-demand triggers
- **Visual Indicators**: Red flashing overlay, confidence scores, AI explanations
- **Alerting System**:
  - Consecutive risk threshold (prevent false alarms)
  - Twilio SMS notifications
  - Webhook integration (n8n, Zapier compatible)
  - Cooldown periods to prevent alert spam
- **Sound Detection** (Optional): Baby cry detection with model FPS display

**Typical Use Cases**:
- Elderly fall detection
- Baby monitoring (unsafe sleeping positions)
- Workplace safety compliance
- Pet monitoring

### 2. Interactive Chat Mode
**Context-aware AI assistant with camera integration**

- **Multi-Provider Support**:
  - Google Gemini (Cloud API)
  - Groq (Cloud API)
  - Ollama (Local LLM)
- **Tool Calling Framework**:
  - `capture_current_frame`: Capture and analyze current video frame with VLM
  - `scrape_web_page`: Web scraping with Playwright + BeautifulSoup
- **Live Camera Context**: Chat agent can "see" the current video feed

**Example Interactions**:
- "What's happening in the camera right now?"
- "Is the baby sleeping safely?"
- "Search the web for X and tell me about it"

### 3. System Controls
- **Video Device Selection**: Switch between `/dev/video0`, `/dev/video1`, etc.
- **Audio Capture** (Optional): ALSA/PulseAudio selection with 5s test recording
- **Real-Time Metrics**: CPU/RAM/GPU usage (psutil + NVIDIA NVML)

---

## 🚀 Quick Start

### Prerequisites
- NVIDIA Jetson Orin Nano/AGX (or compatible Linux system with NVIDIA GPU)
- Docker with NVIDIA runtime (`nvidia-container-toolkit`)
- USB Camera connected to `/dev/video0`
- Ollama installed and running on host: `ollama serve` (port 11434)

### 1. Clone \u0026 Setup
```bash
cd /path/to/VLM_Monitors

# Download MediaMTX (if not already present)
# Place mediamtx binary in temp/mediamtx
```

### 2. Start the Application
```bash
./run.sh up
```

This script will:
- Build the Docker image (if needed)
- Start the container with NVIDIA GPU support
- Expose necessary ports (5000, 8554, 8888)
- Auto-start MediaMTX and camera streaming

### 3. Access the UI
- **Web Interface**: http://localhost:5000
- **RTSP Stream**: rtsp://localhost:8554/camera
- **HLS Stream**: http://localhost:8888/camera/index.m3u8

### 4. Stop the Application
```bash
./run.sh down
```

---

## 📂 Project Structure

```
VLM_Monitors/
├── src/
│   ├── app.py              # Flask application entry point
│   ├── server.py           # Backend server logic, Socket.IO routes
│   ├── shared/
│   │   └── camera.py       # CameraThread (GStreamer + FFmpeg)
│   ├── modes/
│   │   └── risk_detection.py  # Risk detection analysis logic
│   └── tools/
│       ├── image_tools.py  # VLM frame capture tool
│       └── web_tools.py    # Web scraping tool
├── static/
│   ├── index.html          # Frontend HTML
│   ├── css/style.css       # UI styling
│   └── js/app.js           # Frontend JavaScript (HLS.js, Socket.IO)
├── mediamtx.yml            # MediaMTX configuration
├── docker-compose.yml      # Docker Compose setup
├── Dockerfile              # Container image definition
├── requirements.txt        # Python dependencies
├── run.sh                  # Canonical operations script
├── README.md               # User-facing readme (Chinese)
├── spec/
│   ├── PRD.md              # Product requirements document
│   └── PROJECT_MAP.md      # Spec entrypoint
└── specs/
    └── FAQ.md              # Technical FAQ and troubleshooting

Brain Artifacts (Generated):
~/.gemini/antigravity/brain/<conversation-id>/
├── walkthrough.md          # Latest session work summary
├── implementation_plan.md  # Technical implementation plans
└── task.md                 # Task tracking
```

---

## ⚙️ Configuration

### MediaMTX Configuration
**File**: `mediamtx.yml`

**Critical Settings** (modified for low latency):
```yaml
# Enable HLS streaming
hls: yes
hlsAddress: :8888

# ⚠️ CRITICAL: Always generate HLS from RTSP publisher
hlsAlwaysRemux: yes  # Default: no (causes HLS 404 if not set!)

# Low-latency HLS settings
hlsVariant: lowLatency
hlsSegmentDuration: 1s      # Default: 4s (longer = more latency)
hlsPartDuration: 200ms
hlsSegmentCount: 7          # Default: 7

# Explicit camera path
paths:
  camera:
    source: publisher
    runOnReady: echo "Camera stream ready"
```

### HLS.js Player Configuration
**File**: `static/js/app.js`

**Optimized for Low Latency** (buffer reduced from 90s → 1s):
```javascript
hls = new Hls({
    lowLatencyMode: true,
    maxBufferLength: 1,        // 1s max buffer (vs default 30s)
    liveBackBufferLength: 0,   // No back buffer
    liveSyncDuration: 0.5,     // Stay 0.5s from live edge
    liveMaxLatencyDuration: 2, // Drop frames if >2s behind
    // ... (see app.js for full config)
});
```

### Environment Variables
Docker Compose automatically handles most environment variables. For manual runs:
```bash
export GST_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/gstreamer-1.0/
export OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 📊 Performance Benchmarks

### Video Streaming Performance
- **FPS**: 30 FPS (hardware capability, GStreamer pipeline)
- **Internal Processing Latency**: <0.2ms (per frame)
- **End-to-End Latency**: ~1.5-2s (camera → HLS playback)
- **RTSP Latency**: ~100-200ms (real-time)

### AI Inference Performance
- **VLM Analysis**: ~2-5s per frame (depends on Ollama model)
- **Recommended Models**:
  - `llama3.2-vision:11b` (balanced, 11B params)
  - `minicpm-v:8b` (faster, 8B params)
  - `llava:7b` (lightweight, 7B params)

### System Resource Usage
- **CPU**: ~50-60% (multi-threaded camera + inference)
- **RAM**: ~40% (8GB Jetson, with Ollama loaded)
- **GPU**: ~30-40% (H.264 encoding + occasional VLM inference)

---

## 🔧 Troubleshooting

See **[specs/FAQ.md](./specs/FAQ.md)** for detailed troubleshooting guide.

### Common Issues Quick Reference
| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| HLS stream 404 | `hlsAlwaysRemux: no` | Set`hlsAlwaysRemux: yes` in `mediamtx.yml` |
| Video not loading | MediaMTX not started | Check `docker logs llm_monitor \| grep MediaMTX` |
| Low FPS (~10 FPS) | OpenCV backend issue | Use GStreamer pipeline (already implemented) |
| RTSP disconnect | Port conflict or config error | Kill zombie `mediamtx` processes, check port 8554 |
| GPU not detected | NVIDIA runtime missing | Install `nvidia-container-toolkit`, rebuild image |

---

## 📚 Additional Documentation

- **[spec/PROJECT_MAP.md](./spec/PROJECT_MAP.md)**: Progressive-disclosure onboarding map
- **[PRD.md](./PRD.md)**: Product Requirements Document
- **[README.md](./README.md)**: User-facing guide (Chinese)
- **[specs/FAQ.md](./specs/FAQ.md)**: Technical FAQ and lessons learned
- **Walkthrough** (Latest session): `~/.gemini/antigravity/brain/<conversation-id>/walkthrough.md`

---

## 🎯 Current Status \u0026 Known Limitations

### ✅ Working Features
- Real-time video streaming (RTSP + HLS)
- Risk detection with VLM analysis
- Interactive chat mode with tool calling
- SMS and webhook notifications
- HLS latency optimized (<2s end-to-end)

### ⚠️ Known Limitations
1. **Latency**: Currently ~1.5-2s (target was <500ms). Further optimization possible by:
   - Reducing `hlsSegmentDuration` to 200-500ms
   - Switching to WebRTC (complex, requires full rewrite)
2. **Network Sensitivity**: Aggressive HLS buffering may cause stuttering on slow networks
3. **Browser Compatibility**: Low-Latency HLS requires modern browsers (Chrome 90+, Safari 14+)

### 🚧 Future Enhancements
- Implement WebRTC for <100ms latency
- Add multi-camera support
- Implement recording and playback features
- Add more sophisticated risk analysis (object detection, tracking)

---

## 👥 Contributing \u0026 Development

### For AI Agents
Before making changes, **READ [spec/PROJECT_MAP.md](./spec/PROJECT_MAP.md)** and **[specs/FAQ.md](./specs/FAQ.md)** to avoid repeating past mistakes.

### Code Style
- Python: Follow PEP 8, use type hints
- JavaScript: ES6+, camelCase naming
- Document critical sections (especially threading, video pipeline)

### Testing
- Manual testing required for video streaming (no automated tests yet)
- Test on actual Jetson hardware for performance validation
- Verify HLS latency with physical hand-wave test

---

## 📄 License

[Specify license here]

---

**Last Updated**: 2026-02-08  
**Maintainer**: [Your info here]  
**Tested On**: NVIDIA Jetson Orin Nano (8GB), Ubuntu 22.04
