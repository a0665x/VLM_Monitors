# VLM_Monitors - User Manual

## 🛠️ Installation

You can run VLM_Monitors either locally (Python) or using Docker.

### Option A: Docker Installation (Recommended)
This is the easiest way to get started.

1.  **Prerequisites**:
    *   [Docker](https://docs.docker.com/get-docker/) installed.
    *   [Ollama](https://ollama.com/) installed and running on your host machine (`ollama serve`).
    *   Pull a vision model: `ollama pull minicpm-v:8b`

2.  **Run the App**:
    ```bash
    ./run.sh up
    ```
    This script checks Docker, NVIDIA runtime, camera/audio devices, Ollama, the container, Flask API, RTSP, HLS, and device APIs. The app will be accessible at `http://localhost:5000`.

### Option B: Local Python Installation

1.  **Prerequisites**:
    *   Python 3.10+ installed.
    *   [Ollama](https://ollama.com/) installed and running.

2.  **Setup**:
    ```bash
    # Clone the repository (if you haven't already)
    # git clone ...
    # cd VLM_Monitors

    # Create a virtual environment
    python3 -m venv .venv
    source .venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Run**:
    ```bash
    python src/server.py
    ```

## 2. Launching the Application

1.  **Start the App**:
    Run the provided launch script:
    ```bash
    ./run.sh up
    ```
    This script will:
    - Check Docker and NVIDIA runtime.
    - Check host camera/audio devices.
    - Check if Ollama is running.
    - Start the container.
    - Verify the web API, RTSP stream, HLS stream, and device APIs.

2.  **Access the Interface**:
    Open your web browser and go to:
    [http://127.0.0.1:5000](http://127.0.0.1:5000)

## 3. Using the Monitor

### Live Feed
- The **Live Feed** panel shows the real-time video from your camera.
- It starts automatically when the page loads.

### AI Analysis
- **Auto-Analysis**: Check the **"Enable Auto-Analysis"** box to start automatic monitoring.
    - **Scoring Model**: Select the vision model used for risk assessment (e.g., `minicpm-v:8b`, `llama3.2-vision:11b`).
    - **Interval**: Set how often to check (default: 5 seconds).
- **Manual Analysis**: Click "Analyze Next Frame" for a one-off check.
- **Status**:
    - **Monitoring**: Normal state.
    - **Analyzing**: AI is processing a frame.
    - **RISK**: A potential threat has been detected.

### Risk Alerts
- **Visual Alert**: If a risk is detected (e.g., **Person Missing**), the video feed will **flash red**.
- **On-Screen Data**: The system displays **"⚠️ RISK"** (red) or **"✓ SAFE"** (green).
    - **Logging**:
        - Current risk frame is saved to `./temp/short_cut.jpg`.
        - **Detailed Logs**: Full system prompts, user prompts, and raw outputs for every interaction are logged to `./temp/llm.log` with session separators.

### Q&A (Ask LLaVA)
- Type a question in the "LLaVA QA" box (e.g., "Is the person sleeping?").
- Click **Ask LLaVA** to get an answer based on the current video frame.

## 4. Troubleshooting

- **No Camera Feed**:
    - Ensure your USB camera is connected to `/dev/video0`.
    - Check if another application is using the camera.
- **Ollama Error**:
    - Ensure Ollama is running (`ollama serve`).
    - Check if the model is downloaded (`ollama list`).
