"""Read only: advertise a QR target only when Serve routes to this service."""
import json
import subprocess
import os


def get_share_status():
    result = {"ready": False, "url": "", "message": "尚未連接 Tailscale"}
    try:
        def read(*args):
            return json.loads(subprocess.check_output(["tailscale", *args], timeout=3, stderr=subprocess.DEVNULL))
        status = read("status", "--json")
        if status.get("BackendState") != "Running":
            return result
        dns = status.get("Self", {}).get("DNSName", "").rstrip(".")
        result["message"] = "Tailscale 已連線；請在主機執行 ./run.sh local-tailnet 啟用私人分享"
        config = read("serve", "status", "--json")
        port = os.getenv("SERVICE_BIND", "127.0.0.1:5000").rsplit(":", 1)[-1]
        handler = config.get("Web", {}).get(f"{dns}:443", {}).get("Handlers", {}).get("/", {})
        if dns and handler.get("Proxy") in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            if config.get("AllowFunnel", {}).get(f"{dns}:443"):
                result["message"] = "偵測到公開 Funnel，請先停用 Funnel 後使用私人分享"
            else:
                result.update(ready=True, url=f"https://{dns}/join", message="同一個 Tailnet 且具有存取權的裝置可以掃碼觀看")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return result
