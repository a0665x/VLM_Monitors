import subprocess
import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError:
    sd = None
    logger.warning("sounddevice not installed, audio device listing might fail")

class DeviceManager:
    @staticmethod
    def get_video_devices() -> List[Tuple[str, str]]:
        """
        Returns a list of (device_path, device_name) tuples.
        Example: [('/dev/video0', 'Integrated Camera'), ('/dev/video2', 'USB Camera')]
        """
        devices = []
        try:
            # Check if v4l2-ctl is available
            subprocess.check_call(['which', 'v4l2-ctl'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            output = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True)
            lines = output.split('\n')
            
            current_name = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # If line doesn't start with /dev/video, it's likely a name
                if not line.startswith('/dev/video'):
                    # Remove parenthesis info usually at the end
                    current_name = line.split('(')[0].strip()
                    # Remove colon if present
                    if current_name.endswith(':'):
                        current_name = current_name[:-1]
                elif current_name:
                    # It's a device path
                    devices.append((line, current_name))
                    # We only take the first device path for each name usually, 
                    # but v4l2 often lists metadata devices too.
                    # Usually /dev/video0 is capture, /dev/video1 is metadata.
                    # We might want to filter, but for now list all.
                    # Actually, let's reset current_name to handle multiple paths for same device?
                    # No, v4l2 lists name then indented paths.
                    pass
                    
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("v4l2-ctl not found or failed. Falling back to simple glob.")
            import glob
            paths = glob.glob('/dev/video*')
            for p in paths:
                devices.append((p, f"Camera {p}"))
                
        return devices

    @staticmethod
    def get_audio_devices() -> List[Tuple[int, str]]:
        """
        Returns a list of (device_index, device_name) tuples.
        """
        devices = []
        if sd:
            try:
                # sd.query_devices() returns a list of dictionaries
                all_devices = sd.query_devices()
                for i, dev in enumerate(all_devices):
                    # Filter for input devices (max_input_channels > 0)
                    if dev['max_input_channels'] > 0:
                        devices.append((i, f"{dev['name']} (Index {i})"))
            except Exception as e:
                logger.error(f"Error listing audio devices with sounddevice: {e}")
        
        if not devices:
            # Fallback to arecord -l parsing if sounddevice fails or returns nothing
            try:
                output = subprocess.check_output(['arecord', '-l'], text=True)
                # card 0: PCH [HDA Intel PCH], device 0: ALC892 Analog [ALC892 Analog]
                for line in output.split('\n'):
                    if line.startswith('card'):
                        match = re.search(r'card (\d+):.*?device (\d+): (.*?) \[', line)
                        if match:
                            card = match.group(1)
                            device = match.group(2)
                            name = match.group(3)
                            # ALSA device string is usually hw:card,device
                            # But sounddevice uses integer indices.
                            # If we use sounddevice for capture, we need indices.
                            # If we use ffmpeg, we need plughw:x,y.
                            # Since we plan to use sounddevice for capture, we really need it to work.
                            # But if we use ffmpeg for capture?
                            # Let's stick to returning a descriptive string if index is not available.
                            devices.append((-1, f"hw:{card},{device} - {name}"))
            except Exception as e:
                logger.error(f"Error listing audio devices with arecord: {e}")
                
        return devices
