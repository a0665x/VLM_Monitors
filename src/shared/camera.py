import threading
import cv2
import subprocess
import numpy as np
import time
import math
import logging
import re
import os
import queue
import signal
from shared.state import AppState

logger = logging.getLogger(__name__)

class CameraThread(threading.Thread):
    def __init__(self, state: AppState, device="/dev/video0", audio_device="default", rtsp_url="rtsp://localhost:8554/camera"):
        super().__init__(daemon=True)
        self.state = state
        self.device = device
        self.audio_device = audio_device
        self.rtsp_url = rtsp_url
        self.running = True
        self.width = 640
        self.height = 480
        self.fps = 30
        self._threads = []
        self._processes = []
        self._stop_lock = threading.Lock()
        
        # Buffer for RTSP stream (1 frame max to drop old frames)
        self.stream_queue = None
        
    async def _run_inference(self, fc):
        # Placeholder for inference logic if needed
        pass

    def run(self):
        self.stream_queue = queue.Queue(maxsize=1)
        self.raw_queue = queue.Queue(maxsize=2) # Intermediate buffer for raw bytes
        self._select_capture_mode()
        
        logger.info(
            "Starting CameraThread (GStreamer Pipe Mode): %s %sx%s@%sfps -> %s",
            self.device,
            self.width,
            self.height,
            self.fps,
            self.rtsp_url,
        )
        
        # Start Threads
        # 1. Pipeline Reader (Fast, IO bound)
        reader_thread = threading.Thread(target=self._pipe_reader, daemon=True)
        self._threads.append(reader_thread)
        reader_thread.start()
        
        # 2. Frame Processor (Slower, CPU bound)
        processor_thread = threading.Thread(target=self._frame_processor, daemon=True)
        self._threads.append(processor_thread)
        processor_thread.start()
        
        # 3. RTSP Writer
        writer_thread = threading.Thread(target=self._rtsp_writer, daemon=True)
        self._threads.append(writer_thread)
        writer_thread.start()
        
        # Wait for threads to finish (they are daemons so they die with main, but we keep this alive)
        while self.running:
            time.sleep(1)

        self._terminate_processes()

    def stop(self, timeout: float = 2.0):
        with self._stop_lock:
            self.running = False
            self._terminate_processes()

        deadline = time.time() + timeout
        for thread in list(self._threads):
            remaining = max(0.0, deadline - time.time())
            if thread.is_alive() and remaining > 0:
                thread.join(timeout=remaining)

    def _register_process(self, process):
        if process is not None:
            self._processes.append(process)

    def _terminate_processes(self):
        for process in list(self._processes):
            if process.poll() is not None:
                continue
            try:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except Exception:
                        pass
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except Exception:
                    process.terminate()
                process.wait(timeout=0.7)
            except Exception:
                try:
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except Exception:
                        process.kill()
                except Exception:
                    pass

    def _select_capture_mode(self):
        """Pick a capture mode the camera actually advertises."""
        try:
            output = subprocess.check_output(
                ["v4l2-ctl", "-d", self.device, "--list-formats-ext"],
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception as e:
            logger.warning("Could not inspect camera formats for %s: %s", self.device, e)
            return

        modes = []
        current_size = None
        for line in output.splitlines():
            size_match = re.search(r"Size:\s+Discrete\s+(\d+)x(\d+)", line)
            if size_match:
                current_size = (int(size_match.group(1)), int(size_match.group(2)))
                continue

            fps_match = re.search(r"\((\d+(?:\.\d+)?)\s+fps\)", line)
            if current_size and fps_match:
                modes.append((*current_size, int(round(float(fps_match.group(1))))))

        if not modes:
            logger.warning("No discrete camera modes parsed; keeping default %sx%s@%s", self.width, self.height, self.fps)
            return

        preferred = [
            (640, 480, 30),
            (1280, 720, 30),
            (1280, 720, 60),
            (1920, 1080, 30),
        ]
        selected = next((mode for mode in preferred if mode in modes), None)
        if selected is None:
            selected = sorted(modes, key=lambda m: (m[0] * m[1], abs(m[2] - 30)))[0]

        self.width, self.height, self.fps = selected
        logger.info("Selected camera mode: %sx%s@%sfps", self.width, self.height, self.fps)

    def _pipe_reader(self):
        """Reads raw bytes from GStreamer STDOUT as fast as possible."""
        width, height, fps = self.width, self.height, self.fps
        frame_size = width * height * 3 # BGR
        
        # Optimized Pipeline for Jetson: Use nvvidconv for format conversion to reduce CPU load
        # v4l2src (YUY2) -> nvvidconv (BGRx) -> videoconvert (BGR) -> fdsink
        # Note: nvvidconv outputs into NVMM memory usually, but if we don't specify 'memory:NVMM', 
        # it might use standard memory or copy.
        # Safer path that usually works on Jetson for raw capture:
        # Use simple videoconvert but ensure we use leaky queue BEFORE it to drop frames if CPU is busy.
        
        # Actually, let's try to stick to standard videoconvert but ensure exposure is fixed.
        # The logs show FPS dropping to exactly half/quarter -> Exposure issue.
        
        cmd = [
            'gst-launch-1.0', '-q',
            'v4l2src', f'device={self.device}', '!',
            f'video/x-raw,width={width},height={height},framerate={fps}/1,format=YUY2', '!',
            'queue', 'max-size-buffers=1', 'leaky=downstream', '!',
            'videoconvert', '!',
            f'video/x-raw,format=BGR', '!',
            'fdsink', 'sync=false'
        ]
        
        logger.info(f"Capture Command: {' '.join(cmd)}")
        
        # Configure Camera Exposure - COMPREHENSIVE METHOD
        # CRITICAL: Must disable ALL auto-controls to prevent FPS fluctuations
        def set_v4l2(ctrl, val):
            try:
                result = subprocess.run(['v4l2-ctl', '-d', self.device, '-c', f'{ctrl}={val}'], 
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.info(f"✓ Set {ctrl}={val}")
                return True
            except subprocess.CalledProcessError as e:
                # Silent fail - we'll try all variants
                return False

        def get_v4l2(ctrl):
            """Read back a control value to verify it was set"""
            try:
                result = subprocess.run(['v4l2-ctl', '-d', self.device, '-C', ctrl], 
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                # Output format: "control_name: value"
                if ':' in result.stdout:
                    return result.stdout.split(':')[1].strip()
                return None
            except:
                return None

        try:
             logger.info("=== Configuring Camera Controls ===")
             
             # 1. Disable Auto-Focus (prevents refocusing delays)
             set_v4l2('focus_auto', 0)
             set_v4l2('focus_absolute', 0)
             
             # 2. Disable Auto White Balance
             set_v4l2('white_balance_temperature_auto', 0)
             set_v4l2('white_balance_automatic', 0)
             
             # 3. Disable Auto Exposure - TRY ALL VARIANTS
             # Different cameras use different control names
             set_v4l2('exposure_auto', 1)  # 1=Manual for UVC (3=Auto)
             set_v4l2('auto_exposure', 1)  # Alternative name
             set_v4l2('exposure_auto_priority', 0)  # Disable priority (prevents auto-adjust)
             
             # 3.5. CRITICAL: Disable Dynamic Framerate
             # This was the missing piece! Without this, camera adjusts FPS based on exposure
             set_v4l2('exposure_dynamic_framerate', 0)
             
             # 4. Set Absolute Exposure Time
             # Target: 33ms = 30fps
             # Most UVC cameras use 100μs units, so 33ms = 330 units
             # Try both common control names
             exposure_set = False
             for exp_val in [330, 333, 33]:  # Try multiple values
                 if set_v4l2('exposure_absolute', exp_val):
                     exposure_set = True
                     break
                 if set_v4l2('exposure_time_absolute', exp_val):
                     exposure_set = True
                     break
             
             if not exposure_set:
                 logger.warning("⚠ Could not set exposure time - FPS may be unstable")
             
             # 5. Set Fixed Gain (prevent auto-gain causing brightness fluctuations)
             set_v4l2('gain', 100)
             set_v4l2('gain_automatic', 0)
             
             # 6. Verify Critical Settings
             logger.info("=== Verifying Settings ===")
             exp_auto = get_v4l2('exposure_auto') or get_v4l2('auto_exposure')
             exp_time = get_v4l2('exposure_absolute') or get_v4l2('exposure_time_absolute')
             dynamic_fps = get_v4l2('exposure_dynamic_framerate')
             
             if exp_auto:
                 logger.info(f"exposure_auto: {exp_auto} (should be 1=Manual)")
             if exp_time:
                 logger.info(f"exposure_time: {exp_time} (target: 330-333)")
             if dynamic_fps is not None:
                 logger.info(f"dynamic_framerate: {dynamic_fps} (should be 0=Disabled)")
             
             logger.info("=== Camera Configuration Complete ===")
             
        except FileNotFoundError:
             logger.error("v4l2-ctl not found! Install v4l-utils.")
        except Exception as e:
             logger.error(f"Exposure config failed: {e}")
        
        process = None
        try:
            env = os.environ.copy()
            if "/usr/lib/aarch64-linux-gnu/gstreamer-1.0" not in env.get("GST_PLUGIN_PATH", ""):
                 existing = env.get("GST_PLUGIN_PATH", "")
                 env["GST_PLUGIN_PATH"] = f"/usr/lib/aarch64-linux-gnu/gstreamer-1.0/:{existing}"
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, bufsize=10*frame_size, env=env, preexec_fn=os.setsid)
            self._register_process(process)
        except Exception as e:
            logger.error(f"Failed to start Capture GStreamer: {e}")
            return

        frame_count = 0
        last_log_time = time.time()
        
        while self.running:
            try:
                if process.stdout is None:
                    break
                raw_frame = process.stdout.read(frame_size)
                
                if len(raw_frame) != frame_size:
                    logger.warning("Incomplete frame read")
                    if process.poll() is not None:
                        break
                    time.sleep(0.001)
                    continue
                
                # Leaky Put: If processor is slow, drop OLD frame to keep pipe draining
                # We use a small queue (size 2) to buffer slightly but drop aggressively
                try:
                    self.raw_queue.put_nowait((time.time(), raw_frame)) # Add timestamp
                except queue.Full:
                    try:
                        self.raw_queue.get_nowait()
                        self.raw_queue.put_nowait((time.time(), raw_frame))
                    except:
                        pass
                
                # Stats for Reader
                frame_count += 1
                now = time.time()
                if now - last_log_time > 5.0:
                     fps = frame_count / (now - last_log_time)
                     logger.info(f"[READER] FPS: {fps:.2f} | Raw Q: {self.raw_queue.qsize()}")
                     frame_count = 0
                     last_log_time = now
                        
            except Exception as e:
                logger.error(f"Error in pipe reader: {e}")
                break
        
        if process:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except:
                process.kill()

    def _frame_processor(self):
        """Decodes raw bytes and applies processing."""
        width, height = self.width, self.height
        frame_count = 0
        last_log_time = time.time()
        
        while self.running:
            try:
                # Add timeout to loop so we can check self.running
                ts, raw_frame = self.raw_queue.get(timeout=1.0)
                
                # Measure latency (Reader -> Processor start)
                latency_ms = (time.time() - ts) * 1000
                
                # Decode
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
                
                # --- Stats ---
                frame_count += 1
                now = time.time()
                if now - last_log_time > 5.0:
                    fps = frame_count / (now - last_log_time)
                    q_raw = self.raw_queue.qsize()
                    q_rtsp = self.stream_queue.qsize() if self.stream_queue else 0
                    logger.info(f"[PROCESSOR] FPS: {fps:.2f} | Latency: {latency_ms:.1f}ms | Raw Q: {q_raw} | RTSP Q: {q_rtsp}")
                    frame_count = 0
                    last_log_time = now
                
                # --- Processing ---
                frame_working = frame.copy()
                self._apply_overlays(frame_working)
                
                # Update UI
                with self.state.lock:
                    self.state.latest_frame = cv2.cvtColor(frame_working, cv2.COLOR_BGR2RGB)
                
                # Push to RTSP
                try:
                    self.stream_queue.put_nowait(frame_working.copy())
                except queue.Full:
                    pass
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processor: {e}")

    def _rtsp_writer(self):
        """Separate thread to handle GStreamer encoding -> FFmpeg RTSP push."""
        # Hybrid Pipeline: 
        # 1. GStreamer: Raw BGR -> NVENC (Hardware) -> H.264 ByteStream -> STDOUT
        # 2. FFmpeg: STDIN (H.264) -> RTSP (TCP)
        
        rtsp_url = self.rtsp_url
        
        gst_section = (
            "gst-launch-1.0 fdsrc ! "
            f"videoparse width={self.width} height={self.height} format=bgr framerate={self.fps}/1 ! "
            "videoconvert ! nvvidconv ! "
            "nvv4l2h264enc bitrate=2000000 preset-level=1 "
            "profile=0 idrinterval=15 insert-sps-pps=true insert-vui=true ! "
            "h264parse ! video/x-h264,stream-format=byte-stream ! "
            "fdsink"
        )
        
        ffmpeg_section = (
            f"ffmpeg -f h264 -i - "
            f"-c copy -flags low_delay -fflags nobuffer "
            f"-f rtsp -rtsp_transport tcp {rtsp_url}"
        )
        
        full_cmd = f"{gst_section} | {ffmpeg_section}"
        
        logger.info(f"Hybrid Command: {full_cmd}")
        
        process = None
        try:
            # Must ensure GST_PLUGIN_PATH is passed
            env = os.environ.copy()
            if "/usr/lib/aarch64-linux-gnu/gstreamer-1.0" not in env.get("GST_PLUGIN_PATH", ""):
                existing = env.get("GST_PLUGIN_PATH", "")
                env["GST_PLUGIN_PATH"] = f"/usr/lib/aarch64-linux-gnu/gstreamer-1.0/:{existing}"

            # Use shell=True for pipe support
            # Inherit stderr to avoid buffer filling deadlock and see errors in console
            process = subprocess.Popen(full_cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=None, env=env, preexec_fn=os.setsid)
            self._register_process(process)
        except Exception as e:
            logger.error(f"Failed to start Hybrid Pipeline: {e}")
            return

        while self.running:
            try:
                # Wait for frame
                frame = self.stream_queue.get(timeout=0.5)
                try:
                    if process.poll() is not None:
                         logger.warning("RTSP Writer process exited unexpectedly")
                         break
                    if process.stdin is None:
                        break
                    process.stdin.write(frame.tobytes())
                    process.stdin.flush()
                except BrokenPipeError:
                    logger.warning("GStreamer pipe broken")
                    break
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in stream writer: {e}")
                
        if process:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                 process.kill()

    def _apply_overlays(self, img):
        # RTSP Label
        cv2.putText(img, self.rtsp_url, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        sound_risk = getattr(self.state, "sound_risk", False)
        local_selected = getattr(self.state, "selected_source_id", "agx-local") == getattr(self.state, "local_source_id", "agx-local")
        if local_selected and (self.state.risk_binary or sound_risk):
            now = time.time()
            opacity = (math.sin(now * 5) + 1) / 2 * 0.5 + 0.2
            overlay = np.full_like(img, (0, 0, 255))
            cv2.addWeighted(overlay, opacity, img, 1 - opacity, 0, img)
            cv2.rectangle(img, (0, 0), (img.shape[1], img.shape[0]), (0, 0, 255), 20)
            cv2.putText(img, "RISK DETECTED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            
        if self.state.auto_analyze and local_selected:
            cv2.putText(img, "AUTO: ON", (10, img.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

# Helper to scan devices
import functools

@functools.lru_cache(maxsize=1)
def get_video_devices():
    import glob
    grouped_devices = []
    try:
        output = subprocess.check_output(
            ["v4l2-ctl", "--list-devices"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2,
        )
        current_group = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                if current_group:
                    grouped_devices.append(current_group)
                    current_group = []
                continue
            if stripped.startswith("/dev/video"):
                current_group.append(stripped)
        if current_group:
            grouped_devices.append(current_group)
    except Exception:
        grouped_devices = []

    candidates = []
    if grouped_devices:
        candidates = [dev for group in grouped_devices for dev in group]
    else:
        candidates = sorted(glob.glob("/dev/video*"))

    usable = []
    seen_groups = set()
    for dev in candidates:
        try:
            output = subprocess.check_output(
                ["v4l2-ctl", "-d", dev, "--list-formats-ext"],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=2,
            )
            if "Video Capture" in output and "Size: Discrete" in output:
                group_key = next((idx for idx, group in enumerate(grouped_devices) if dev in group), dev)
                if group_key not in seen_groups:
                    usable.append(dev)
                    seen_groups.add(group_key)
        except Exception:
            continue
    return usable if usable else ["/dev/video0"]

@functools.lru_cache(maxsize=1)
def get_audio_devices():
    devices = ["default"]
    pulse_entries = 0
    try:
        output = subprocess.check_output(['arecord', '-l']).decode('utf-8')
        for line in output.splitlines():
            match = re.search(r'card (\d+): .*? \[(.*?)\], device (\d+): .*? \[(.*?)\]', line)
            if match:
                card_id = match.group(1)
                card_name = match.group(2)
                dev_id = match.group(3)
                dev_name = match.group(4)
                alsa_dev = f"hw:{card_id},{dev_id}"
                label = f"{card_name} - {dev_name} ({alsa_dev})"
                devices.append(label)
    except Exception as e:
        logger.error(f"Error listing audio devices: {e}")
        
    try:
        output = subprocess.check_output(['pactl', 'list', 'sources', 'short']).decode('utf-8')
        for line in output.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]
                if "monitor" not in name:
                    label = f"Pulse: {name}"
                    devices.append(f"{label} (pulse:{name})")
                    pulse_entries += 1
    except Exception as e:
        logger.warning(f"PulseAudio not available: {e}")
 
    if pulse_entries == 0 and os.getenv("PULSE_SERVER"):
         devices.append("Pulse: default (pulse:default)")
        
    return devices
