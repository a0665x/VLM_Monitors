"""Same-origin WebRTC signaling and local MediaMTX discovery."""
import ipaddress
import subprocess
from pathlib import Path
import httpx


def prepare_media_config(config_path):
    """Only extend our loopback profile after private Serve has been enabled."""
    from services.tailnet import get_share_status
    if not get_share_status().get('ready'):
        return config_path
    text = Path(config_path).read_text()
    if 'webrtcLocalUDPAddress: 127.0.0.1:8189' not in text:
        return config_path
    try:
        address = subprocess.check_output(['tailscale', 'ip', '-4'], timeout=3, text=True).strip()
        if ipaddress.ip_address(address) not in ipaddress.ip_network('100.64.0.0/10'):
            return config_path
        text = text.replace('webrtcLocalUDPAddress: 127.0.0.1:8189',
                            f'webrtcLocalUDPAddress: {address}:8189\nwebrtcLocalTCPAddress: {address}:8189')
        text = text.replace('webrtcAdditionalHosts: [127.0.0.1]', f'webrtcAdditionalHosts: [{address}]')
        text += '\napi: yes\napiAddress: 127.0.0.1:9997\n'
        target = Path('temp/mediamtx.tailnet.yml')
        target.write_text(text)
        return str(target)
    except (OSError, ValueError, subprocess.SubprocessError):
        return config_path


def live_paths():
    response = httpx.get('http://127.0.0.1:9997/v3/paths/list?itemsPerPage=1000', timeout=2)
    response.raise_for_status()
    return {p['name']: p for p in response.json().get('items', []) if p.get('ready')}


def rewrite_location(location):
    from urllib.parse import urlsplit
    parsed = urlsplit(location)
    if parsed.netloc and parsed.hostname not in {'127.0.0.1', 'localhost'}:
        raise ValueError('Unexpected MediaMTX redirect')
    path = parsed.path
    if not path.startswith('/'):
        return location
    return '/proxy/webrtc' + path + (('?' + parsed.query) if parsed.query else '')
