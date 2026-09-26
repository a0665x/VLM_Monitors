import json
import httpx
import pytest
from src.adapters.vllm_client import VLLMClient
from src.adapters.inference_client import create_inference_client, backend_name, default_model


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_vllm_sends_image_and_reads_completion(monkeypatch):
    monkeypatch.setenv('VLM_MAX_TOKENS', '64')
    def handler(request):
        assert str(request.url) == 'http://test/v1/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'vision-test'
        assert body['max_tokens'] == 64
        assert body['messages'][1]['content'][1]['image_url']['url'] == 'data:image/jpeg;base64,aW1hZ2U='
        return httpx.Response(200, json={'model': 'vision-test', 'choices': [{'message': {'content': 'YES. Visible hazard.'}}]})
    mock_client(monkeypatch, handler)
    result = await VLLMClient('http://test/v1').generate('system', 'question', b'image', 'vision-test')
    assert result.risk is True
    assert result.model == 'vision-test'


@pytest.mark.asyncio
async def test_vllm_stream_handles_empty_usage_and_done(monkeypatch):
    chunks = []
    data = 'data: {"choices":[{"delta":{"content":"NO"}}]}\n\n'
    data += 'data: {"choices":[{"delta":{"content":". Clear."}}]}\n\n'
    data += 'data: {"choices":[],"usage":{}}\n\ndata: [DONE]\n\n'
    mock_client(monkeypatch, lambda r: httpx.Response(200, text=data, headers={'content-type':'text/event-stream'}))
    result = await VLLMClient('http://test/v1').generate_stream('s','u',on_chunk=lambda text,done: chunks.append((text,done)))
    assert result.text == 'NO. Clear.'
    assert result.risk is False
    assert chunks[-1] == ('NO. Clear.', True)


@pytest.mark.asyncio
async def test_vllm_http_failure_is_not_a_successful_result(monkeypatch):
    mock_client(monkeypatch, lambda r: httpx.Response(503, json={'error':'model unavailable'}))
    with pytest.raises(httpx.HTTPStatusError):
        await VLLMClient('http://test/v1').generate('s','u')


def test_factory_uses_explicit_backend_and_model(monkeypatch):
    monkeypatch.setenv('VLM_BACKEND','vllm')
    monkeypatch.setenv('VLM_MODEL','served-vision-model')
    assert isinstance(create_inference_client(), VLLMClient)
    assert default_model() == 'served-vision-model'
    monkeypatch.setenv('VLM_BACKEND','typo')
    with pytest.raises(ValueError):
        backend_name()


def test_service_contract_has_relative_playback_path(monkeypatch):
    import src.server as server
    from src.shared.state import AppState
    monkeypatch.setattr(server, 'app_state', AppState())
    client = server.app.test_client()
    assert client.get('/api/service').get_json()['api_version'] == 1
    source = client.get('/api/sources').get_json()['sources'][0]
    assert source['hls_proxy_path'] == '/proxy/hls/camera/index.m3u8'


def test_camera_explicit_device_overrides_environment(monkeypatch):
    from src.shared.camera import CameraThread
    from src.shared.state import AppState
    monkeypatch.setenv('VIDEO_DEVICE', '/dev/video0')
    assert CameraThread(AppState(), device='/dev/video2').device == '/dev/video2'
    assert CameraThread(AppState()).device == '/dev/video0'


def test_hls_proxy_keeps_session_query_and_byte_range(monkeypatch):
    import src.server as server
    class Upstream:
        status = 206
        headers = {'Content-Type':'video/mp4', 'Content-Range':'bytes 0-3/100', 'Accept-Ranges':'bytes'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'data'
    def open_upstream(request, timeout):
        assert request.full_url == 'http://127.0.0.1:8888/camera/part.mp4?session=abc&_HLS_msn=3'
        assert request.get_header('Range') == 'bytes=0-3'
        return Upstream()
    monkeypatch.setattr(server.urllib_request, 'urlopen', open_upstream)
    response = server.app.test_client().get('/proxy/hls/camera/part.mp4?session=abc&_HLS_msn=3', headers={'Range':'bytes=0-3'})
    assert response.status_code == 206
    assert response.headers['Content-Range'] == 'bytes 0-3/100'
    assert response.data == b'data'
