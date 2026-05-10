import cv2
import time
import sys

def verify_latency(source=0, title="Camera Latency Test"):
    print(f"--- {title} ---")
    print(f"Opening source: {source}")
    
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Failed to open source: {source}")
        return

    # Try to set buffer size to 1 if possible
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
            
            # Simulate some processing time to see if buffer improved
            # time.sleep(0.05) 
            
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
    # Check build info first
    print(cv2.getBuildInformation())
    
    # Check GStreamer availability explicitly
    gst_available = False
    try:
        # This might fail if not compiled with GST
        print(f"GStreamer Backend Available: {cv2.CAP_GSTREAMER}") 
        gst_available = True
    except AttributeError:
        print("GStreamer Backend NOT Available in cv2 module")

    if len(sys.argv) > 1:
        source = sys.argv[1]
        verify_latency(source, f"Custom Source: {source}")
    else:
        verify_latency(0, "V4L2 Default")
