# Product Requirements Document (PRD) - LLM Monitor

## 1. Introduction
LLM Monitor is a local-first camera monitoring and agent app with two modes: a risk detection dashboard and an interactive chat agent. It is designed for Jetson-class devices, keeps video on-device, and uses Ollama for on-box vision inference.

## 2. Goals & Objectives
- **Real-time Monitoring**: Provide a continuous live video feed with low-latency streaming.
- **Intelligent Risk Analysis**: Detect unsafe situations using a customizable risk prompt and vision models.
- **Privacy First**: Run inference locally (Ollama) and keep video on the device.
- **Interactive Agent Mode**: Support chat-based Q&A with tool calling and camera context.
- **Operational Alerts**: Notify caregivers/operators via SMS and webhooks with cooldown/threshold controls.

## 3. Features

### 3.1 Live Video + Streaming
- **Description**: Continuous camera feed published to RTSP and previewed in the UI.
- **Streaming**: FFmpeg publishes to MediaMTX (RTSP + HLS endpoints).
- **UI Preview**: Streamlit WebRTC preview uses the shared camera thread.

### 3.2 Risk Detection Mode
- **Prompt-driven Analysis**: User-defined risk criteria with history.
- **Auto/Manual Analysis**: Interval-based auto analysis plus one-shot trigger.
- **Risk Indicators**: Visual red overlay, status label, confidence, and explanation.
- **Thresholding**: Consecutive risk count threshold before alerting.
- **Alerts**: Twilio SMS and webhook pushes with cooldown.

### 3.3 Interactive Chat Mode
- **Providers**: Gemini, Groq, and Ollama.
- **Tool Calling**: Enable/disable tools per session.
- **Tools Included**:
  - `capture_current_frame` (Ollama VLM description)
  - `scrape_web_page` (Playwright + BeautifulSoup)

### 3.4 Device & System Controls
- **Video Device Selection**: Switch `/dev/video*` sources.
- **Audio Capture (Optional)**: ALSA/Pulse selection with 5s recording test.
- **System Metrics**: CPU/RAM/GPU usage via psutil + NVML.

### 3.5 Observability
- **Logs**: `temp/app.log` (app), `temp/llm.log` (prompt + responses).
- **Snapshots**: `temp/short_cut.jpg` for the latest analyzed frame.

## 4. Technical Architecture

### 4.1 Technology Stack
- **Language**: Python 3.10 (Docker) / Python 3.11 supported
- **UI Framework**: Streamlit + streamlit-webrtc
- **Computer Vision**: OpenCV (cv2)
- **Streaming**: FFmpeg + MediaMTX (RTSP/HLS)
- **AI Inference**: Ollama (vision models like `llama3.2-vision:11b`, `minicpm-v:8b`)
- **Chat Providers**: Gemini, Groq, Ollama (OpenAI-compatible tooling)
- **Notifications**: Twilio SMS + webhook POST

### 4.2 System Components
1. **CameraThread**: Captures frames, overlays risk state, and publishes RTSP.
2. **InferenceEngine**: Runs VLM risk checks and logs interactions.
3. **Streamlit UI**: Mode router, controls, live preview, and chat interface.
4. **MediaMTX**: RTSP/HLS server on host network.

## 5. Hardware Requirements
- **Platform**: NVIDIA Jetson Orin Nano (or compatible Linux system).
- **Camera**: USB Webcam (`/dev/video0`).
- **Memory**: 8GB+ recommended for local VLMs.
