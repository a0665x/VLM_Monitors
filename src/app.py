"""Main entrypoint for the LLM Monitor."""
import streamlit as st
from modes import risk_detection, interactive_chat

# Global Page Config
st.set_page_config(
    page_title="LLM Monitor",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- System Setup ---
import os
import subprocess
import time

# 1. Setup GStreamer Plugin Path for NVIDIA Acceleration
if "GST_PLUGIN_PATH" not in os.environ:
    os.environ["GST_PLUGIN_PATH"] = "/usr/lib/aarch64-linux-gnu/gstreamer-1.0/"

# 2. Ensure RTSP Server (MediaMTX) is running
def ensure_mediamtx():
    try:
        # Check if pgrep exists and use it to find mediamtx
        subprocess.check_call(["pgrep", "-x", "mediamtx"], stdout=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not running or pgrep not found, try to start
        # Assume we are in project root
        mtx_path = "./temp/mediamtx"
        if os.path.exists(mtx_path):
            print("🚀 Starting MediaMTX...")
            subprocess.Popen([mtx_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        else:
            print(f"⚠️ MediaMTX binary not found at {mtx_path}")

ensure_mediamtx()
# --------------------

def main():
    if "mode" not in st.session_state:
        st.session_state.mode = None

    # Landing Page
    if st.session_state.mode is None:
        st.title("LLM Monitor & Agent Hub")
        st.markdown("### Select a Mode to Begin")
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.header("🛡️ Risk Detection")
                st.markdown("Real-time video analysis for threat detection using VLLMs.")
                if st.button("Launch Risk Monitor", use_container_width=True):
                    st.session_state.mode = "risk"
                    st.rerun()
                    
        with col2:
            with st.container(border=True):
                st.header("💬 Interactive Chat")
                st.markdown("Chat with LLMs and use tools like Web Scraping.")
                if st.button("Launch Chat Agent", use_container_width=True):
                    st.session_state.mode = "chat"
                    st.rerun()
                    
    # Mode Routing
    elif st.session_state.mode == "risk":
        if st.sidebar.button("← Back to Home"):
            # Cleanup Camera
            if "app_state" in st.session_state:
                state = st.session_state.app_state
                if hasattr(state, 'camera_thread') and state.camera_thread and state.camera_thread.is_alive():
                    state.camera_thread.running = False
                    state.camera_thread.join(timeout=1.0)
                    state.camera_thread = None
                if hasattr(state, 'sound_thread') and state.sound_thread and state.sound_thread.is_alive():
                    state.sound_thread.stop()
                    state.sound_thread.join(timeout=1.0)
                    state.sound_thread = None
            st.session_state.mode = None
            st.rerun()
        risk_detection.run()
        
    elif st.session_state.mode == "chat":
        if st.sidebar.button("← Back to Home"):
             # Cleanup Camera
            if "app_state" in st.session_state:
                state = st.session_state.app_state
                if hasattr(state, 'camera_thread') and state.camera_thread and state.camera_thread.is_alive():
                    state.camera_thread.running = False
                    state.camera_thread.join(timeout=1.0)
                    state.camera_thread = None
                if hasattr(state, 'sound_thread') and state.sound_thread and state.sound_thread.is_alive():
                    state.sound_thread.stop()
                    state.sound_thread.join(timeout=1.0)
                    state.sound_thread = None
            st.session_state.mode = None
            st.rerun()
        interactive_chat.run()

if __name__ == "__main__":
    main()
