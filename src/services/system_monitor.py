import psutil
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SystemMonitor:
    _instance = None
    _nvml_initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemMonitor, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
            
            # Try to get basic GPU info to verify access
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                logger.info(f"✓ NVML initialized successfully. GPU: {name}")
            except Exception as verify_error:
                logger.warning(f"NVML init succeeded but cannot access GPU: {verify_error}")
                
        except ModuleNotFoundError:
            logger.error("nvidia-ml-py not installed. Run: pip install nvidia-ml-py")
            self._nvml_initialized = False
        except Exception as e:
            error_msg = str(e)
            if "NVML Shared Library Not Found" in error_msg or "libnvidia-ml.so" in error_msg:
                logger.warning("NVIDIA driver not found. GPU metrics unavailable (normal in CPU-only environments)")
            elif "Insufficient Permissions" in error_msg or "Permission denied" in error_msg:
                logger.error("Cannot access GPU - insufficient permissions. Docker needs: --gpus all or --runtime=nvidia")
            else:
                logger.warning(f"Failed to initialize NVML: {e}. GPU metrics will be unavailable.")
            self._nvml_initialized = False

    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram": self._get_ram_metrics(),
            "gpu": self._get_gpu_metrics()
        }
        return metrics

    def _get_ram_metrics(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent
        }

    def _get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        # Try Jetson/Tegra GPU first (use tegrastats)
        jetson_gpu = self._get_jetson_gpu_metrics()
        if jetson_gpu:
            return jetson_gpu
            
        # Fall back to pynvml for standard NVIDIA GPUs
        if not self._nvml_initialized:
            return None
        
        try:
            import pynvml
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            return {
                "name": name,
                "total_gb": round(info.total / (1024**3), 2),
                "used_gb": round(info.used / (1024**3), 2),
                "free_gb": round(info.free / (1024**3), 2),
                "memory_percent": round((info.used / info.total) * 100, 1),
                "utilization_percent": util.gpu
            }
        except Exception as e:
            logger.debug(f"Error fetching GPU metrics: {e}")
            return None
    
    def _get_jetson_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Get GPU metrics from Jetson/Tegra using tegrastats."""
        try:
            import subprocess
            import re
            
            output = ""
            try:
                result = subprocess.run(
                    ['tegrastats', '--interval', '100', '--count', '1'],
                    capture_output=True,
                    text=True,
                    timeout=2.0
                )
                if result.returncode == 0 and "RAM" in result.stdout and "GR3D_FREQ" in result.stdout:
                    output = result.stdout
            except subprocess.TimeoutExpired:
                output = ""

            if not output:
                process = subprocess.Popen(
                    ['tegrastats', '--interval', '100'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                try:
                    output = process.stdout.readline() if process.stdout else ""
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()

            if not output:
                return None
            
            # Parse tegrastats output
            # Example: RAM 8234/31893MB (lfb 192x4MB) SWAP 0/15946MB (cached 0MB) CPU [22%@1190,17%@1190,19%@1190,19%@1190,15%@1190,16%@1190] GR3D_FREQ 670Mhz VIC_FREQ 525Mhz NVENC 16800000 NVDEC 16800000 EMC_FREQ 2%@2132Mhz GPU@35C SOC1@35.5C SOC0@36C CV0@35C
            
            gpu_freq_match = re.search(r'GR3D_FREQ\s+(\d+)%?(?:@(\d+))?', output)
            ram_match = re.search(r'RAM\s+(\d+)/(\d+)MB', output)
            
            gpu_util = 0
            if gpu_freq_match:
                first_value = int(gpu_freq_match.group(1))
                if "%" in gpu_freq_match.group(0):
                    gpu_util = min(100, first_value)
                else:
                    # Older tegrastats output can expose frequency without utilization.
                    gpu_util = min(100, int((float(first_value) / 1300.0) * 100))
            
            total_mem = 0
            used_mem = 0
            if ram_match:
                used_mem = int(ram_match.group(1)) / 1024  # Convert to GB
                total_mem = int(ram_match.group(2)) / 1024
            
            return {
                "name": "Jetson Tegra GPU",
                "total_gb": round(total_mem, 2),
                "used_gb": round(used_mem, 2),
                "free_gb": round(max(0, total_mem - used_mem), 2),
                "memory_percent": round((used_mem / total_mem * 100) if total_mem > 0 else 0, 1),
                "utilization_percent": gpu_util
            }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            # tegrastats not available or failed
            logger.debug(f"Jetson GPU metrics not available: {e}")
            return None

    def __del__(self):
        if self._nvml_initialized:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except:
                pass
