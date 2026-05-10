import sounddevice as sd
import numpy as np
import time

chunk_count = 0
def audio_callback(indata, frames, time_info, status):
    global chunk_count
    audio_window = indata.copy()[:, 0]
    peak = np.max(np.abs(audio_window))
    audio_window_dc = audio_window - np.mean(audio_window)
    rms = float(np.sqrt(np.mean(np.square(audio_window_dc))) + 1e-9)
    db = 20.0 * np.log10(rms)
    print(f"Peak: {peak:.2f}, RMS: {rms:.6f}, DB: {db:.2f}", flush=True)
    chunk_count += 1
    if chunk_count > 5:
        raise sd.CallbackStop()

try:
    with sd.InputStream(channels=1, samplerate=16000, dtype="float32", callback=audio_callback):
        sd.sleep(1000)
except Exception as e:
    print(f"Stream stopped: {e}")
