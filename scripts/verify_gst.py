import cv2
import time
import sys

def verify_gst_latency(device="/dev/video0"):
    print(f"--- GStreamer Latency Test ---")
    
    # Simple GST pipeline for raw video
    # v4l2src -> decoding -> appsink
    pipeline = (
        f"v4l2src device={device} ! "
        "video/x-raw,framerate=30/1 ! "
        "videoconvert ! "
        "appsink drop=1"
    )
    
    print(f"Pipeline: {pipeline}")
    
    try:
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    except Exception as e:
        print(f"Error creating GST capture: {e}")
        return

    if not cap.isOpened():
        print("Failed to open GStreamer pipeline")
        return

    print("Reading frames... Press Ctrl+C to stop.")
    
    frame_count = 0
    start_time = time.time()
    prev_time = start_time
    
    try:
        while True:
            read_start = time.time()
            ret, frame = cap.read()
            read_end = time.time()
            
            if not ret:
                print("Failed to read frame")
                break
                
            frame_count += 1
            now = time.time()
            
            if now - prev_time >= 1.0:
                fps = frame_count / (now - prev_time)
                print(f"FPS: {fps:.2f} | Read Time: {(read_end - read_start)*1000:.2f}ms")
                frame_count = 0
                prev_time = now
                
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cap.release()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        verify_gst_latency(sys.argv[1])
    else:
        verify_gst_latency()
