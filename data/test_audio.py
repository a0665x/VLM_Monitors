import sounddevice as sd
import numpy as np
import time

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)
    audio_window = indata.copy()[:, 0]
    audio_window = audio_window - np.mean(audio_window)
    rms = float(np.sqrt(np.mean(np.square(audio_window))) + 1e-9)
    db = max(-120.0, min(0.0, 20.0 * np.log10(rms)))
    level = np.abs(audio_window).max()
    print(f"RMS: {rms:.6f}, Peak: {level:.6f}, DB: {db:.2f}", flush=True)

try:
    print("Starting stream...", flush=True)
    with sd.InputStream(channels=1, samplerate=16000, dtype="float32", callback=audio_callback):
        sd.sleep(3000)
except Exception as e:
    print(f"Error: {e}", flush=True)
