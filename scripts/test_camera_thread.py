import sys
import os
sys.path.append(os.path.join(os.getcwd(), "src"))
import time
import threading
from shared.camera import CameraThread
from shared.state import AppState
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_camera_thread():
    print("Initializing AppState...")
    state = AppState()
    
    # Create CameraThread
    # Note: We use the default device (usually /dev/video0)
    print("Starting CameraThread...")
    cam_thread = CameraThread(state)
    cam_thread.start()
    
    try:
        # Run until interrupted
        print("Running forever. Press Ctrl+C to stop.")
        while True:
            with state.lock:
                if state.latest_frame is not None:
                    # Just print resolution to confirm we have frames
                    h, w, _ = state.latest_frame.shape
                    # print(f"Frame received: {w}x{h}", end='\r')
            time.sleep(1)
            
        print("\nTest finished. Stopping thread...")
    except KeyboardInterrupt:
        print("\nTest interrupted.")
    finally:
        cam_thread.running = False
        cam_thread.join(timeout=2.0)
        print("CameraThread stopped.")

if __name__ == "__main__":
    test_camera_thread()
