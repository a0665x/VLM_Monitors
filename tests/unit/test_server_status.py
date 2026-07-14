from src.server import app, build_status_payload
import src.server as server
from src.shared.state import AppState


class StubAnalysisThread:
    def __init__(self) -> None:
        self.auto_values = []
        self.notify_calls = []

    def set_auto_analyze(self, enabled: bool) -> None:
        self.auto_values.append(enabled)

    def notify_config_changed(self, immediate: bool = False) -> None:
        self.notify_calls.append(immediate)


def test_build_status_payload_exposes_analysis_and_notification_settings():
    state = AppState()
    state.auto_analyze = True
    state.analysis_interval = 7
    state.risk_threshold = 4
    state.alert_cooldown = 180
    state.enable_sms = False
    state.enable_webhook = True
    state.alert_receiver = "+15551234567"
    state.custom_msg = "Alert now"
    state.webhook_url = "https://example.com/hook"

    payload = build_status_payload(state)

    assert payload["auto_analyze"] is True
    assert payload["analysis_interval"] == 7
    assert payload["risk_threshold"] == 4
    assert payload["alert_cooldown"] == 180
    assert payload["enable_sms"] is False
    assert payload["enable_webhook"] is True
    assert payload["alert_receiver"] == "+15551234567"
    assert payload["custom_msg"] == "Alert now"
    assert payload["webhook_url"] == "https://example.com/hook"


def test_toggle_auto_analysis_off_resets_detection_state():
    test_state = AppState()
    test_state.auto_analyze = True
    test_state.analysis_running = True
    test_state.risk_binary = True
    test_state.risk_score = 0.9
    test_state.consecutive_risk_count = 3

    stub_thread = StubAnalysisThread()
    server.app_state = test_state
    server.analysis_thread = stub_thread

    client = app.test_client()
    response = client.post("/api/analysis/auto", json={"enabled": False})

    assert response.status_code == 200
    assert response.get_json()["enabled"] is False
    assert stub_thread.auto_values == [False]
    assert test_state.analysis_running is False
    assert test_state.risk_binary is False
    assert test_state.risk_score == 0.0
    assert test_state.consecutive_risk_count == 0
    assert test_state.risk_explanation == "Auto analysis disabled."


def test_notification_settings_route_updates_notifier_webhook():
    test_state = AppState()
    server.app_state = test_state

    client = app.test_client()
    response = client.post(
        "/api/config/notifications",
        json={
            "enable_sms": True,
            "enable_webhook": True,
            "webhook_url": "https://example.com/webhook"
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["status"]
    assert payload["enable_sms"] is True
    assert payload["enable_webhook"] is True
    assert payload["webhook_url"] == "https://example.com/webhook"
    assert test_state.notifier.webhook_url == "https://example.com/webhook"


def test_situation_room_mode_allows_shared_clients():
    test_state = AppState()
    server.app_state = test_state

    client = app.test_client()

    first = client.post(
        "/api/mode",
        json={"mode": "situation", "client_id": "room-a", "source_id": "agx-local"},
    )
    assert first.status_code == 200
    assert first.get_json()["mode"] == "situation"
    assert test_state.situation_room_client_id == ""

    second = client.post(
        "/api/mode",
        json={"mode": "situation", "client_id": "room-b", "source_id": "agx-local"},
    )
    assert second.status_code == 200
    assert second.get_json()["mode"] == "situation"
    assert test_state.situation_room_client_id == ""


def test_camera_mode_registers_remote_source_only_when_requested():
    test_state = AppState()
    server.app_state = test_state

    client = app.test_client()
    idle_response = client.post(
        "/api/mode",
        json={
            "mode": "camera",
            "client_id": "phone-a-client",
            "source_id": "phone-a",
            "label": "Phone A",
        },
    )

    assert idle_response.status_code == 200
    assert idle_response.get_json()["mode"] == "camera"
    assert "phone-a" not in test_state.sources

    publish_response = client.post(
        "/api/mode",
        json={
            "mode": "camera",
            "client_id": "phone-a-client",
            "source_id": "phone-a",
            "label": "Phone A",
            "register_source": True,
        },
    )

    assert publish_response.status_code == 200
    assert "phone-a" in test_state.sources
    assert test_state.sources["phone-a"]["label"] == "Phone A"
    assert test_state.sources["phone-a"]["status"] == "online"


def test_select_source_resets_risk_and_switches_selected_source():
    test_state = AppState()
    test_state.risk_binary = True
    test_state.risk_score = 0.88
    test_state.consecutive_risk_count = 3
    test_state.risk_explanation = "Old source risk"
    test_state.sources["phone-a"] = {
        "id": "phone-a",
        "label": "Phone A",
        "kind": "remote",
        "status": "online",
        "last_seen": 1.0,
        "updated_at": "",
        "is_local": False,
    }
    server.app_state = test_state

    client = app.test_client()
    response = client.post("/api/sources/select", json={"source_id": "phone-a"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_source_id"] == "phone-a"
    assert test_state.selected_source_id == "phone-a"
    assert test_state.selected_source_label == "Phone A"
    assert test_state.risk_binary is False
    assert test_state.risk_score == 0.0
    assert test_state.consecutive_risk_count == 0
    assert test_state.risk_explanation == "Selected source switched to Phone A."


def test_invalid_selected_source_falls_back_to_local():
    test_state = AppState()
    test_state.sources["phone-a"] = {
        "id": "phone-a",
        "label": "Phone A",
        "kind": "remote",
        "status": "offline",
        "last_seen": 0.0,
        "updated_at": "",
        "is_local": False,
    }
    test_state.selected_source_id = "phone-a"
    test_state.selected_source_label = "Phone A"
    server.app_state = test_state

    server.ensure_valid_selected_source()

    assert test_state.selected_source_id == test_state.local_source_id
    assert test_state.selected_source_label == "AGX Local Camera"
    assert test_state.risk_explanation == "Selected source switched to AGX Local Camera."


def test_disconnect_remote_source_removes_tile_and_falls_back_to_local():
    test_state = AppState()
    test_state.sources["phone-a"] = {
        "id": "phone-a",
        "label": "Phone A",
        "kind": "remote",
        "status": "online",
        "last_seen": 1.0,
        "updated_at": "",
        "is_local": False,
    }
    test_state.selected_source_id = "phone-a"
    test_state.selected_source_label = "Phone A"
    server.app_state = test_state

    client = app.test_client()
    response = client.post("/api/sources/disconnect", json={"source_id": "phone-a"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["disconnected_source_id"] == "phone-a"
    assert "phone-a" not in test_state.sources
    assert test_state.selected_source_id == test_state.local_source_id
    assert test_state.selected_source_label == "AGX Local Camera"
