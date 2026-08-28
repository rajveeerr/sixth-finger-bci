import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.settings import Settings


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["synthetic"] is True
    assert len(body["model_sha256"]) == 64


def test_info_and_trials(client):
    info = client.get("/api/info").json()
    assert info["n_trials"] == 4
    assert info["display_channels"][1] == "C3"
    trials = client.get("/api/trials").json()
    assert [t["label"] for t in trials] == ["affected_hand", "sixth_finger"] * 2


def _collect(ws, until_type: str, limit: int = 20_000) -> list[dict]:
    messages = []
    for _ in range(limit):
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == until_type:
            return messages
    raise AssertionError(f"no {until_type!r} message after {limit} messages")


def test_trial_mode_stream(client):
    with client.websocket_connect("/ws/stream?speed=10000&loop=false") as ws:
        messages = _collect(ws, "end")
    kinds = [m["type"] for m in messages]
    assert kinds[0] == "hello"
    assert kinds.count("trial_start") == 4
    predictions = [m for m in messages if m["type"] == "prediction"]
    assert len(predictions) == 8
    assert all(m["correct"] for m in predictions)
    first = predictions[1]
    assert first["window"] == "imagery"
    assert first["truth"] == "affected_hand"
    assert first["command"] == "HAND_GRASP"
    assert abs(sum(first["probs"]) - 1) < 1e-3
    eeg = next(m for m in messages if m["type"] == "eeg")
    assert len(eeg["data"]) == 7
    assert len(eeg["data"][0]) == 10


def test_truth_is_hidden_until_the_cue(client):
    with client.websocket_connect("/ws/stream?speed=10000&loop=false") as ws:
        messages = _collect(ws, "trial_end")
    order = [m["type"] if m["type"] != "phase" else m["phase"] for m in messages]
    imagery_at = order.index("imagery")
    rest_prediction_at = next(
        i for i, m in enumerate(messages) if m["type"] == "prediction" and m["window"] == "rest"
    )
    imagery_prediction_at = next(
        i for i, m in enumerate(messages) if m["type"] == "prediction" and m["window"] == "imagery"
    )
    assert rest_prediction_at < imagery_at < imagery_prediction_at
    prepare = next(m for m in messages if m.get("phase") == "prepare")
    assert prepare["truth"] is None


def test_continuous_mode_is_flagged_experimental(client):
    with client.websocket_connect("/ws/stream?mode=continuous&speed=10000&loop=false") as ws:
        messages = _collect(ws, "end")
    sliding = [m for m in messages if m["type"] == "prediction"]
    assert sliding and all(m["window"] == "sliding" and m["experimental"] for m in sliding)
    assert {m["command"] for m in sliding} <= {"IDLE", "HAND_GRASP", "SIXTH_FINGER_FLEX"}


def test_controls_pause_and_jump(client):
    with client.websocket_connect("/ws/stream?speed=10000") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "jump", "trial": 3})
        seen_status, trial_starts = False, []
        for _ in range(5000):
            message = ws.receive_json()
            if message["type"] == "status":
                seen_status = True
            if message["type"] == "trial_start":
                trial_starts.append(message["trial"])
                if 3 in trial_starts:
                    break
        assert seen_status
        assert 3 in trial_starts
        ws.send_json({"type": "nonsense"})
        for _ in range(5000):
            if ws.receive_json()["type"] == "error":
                break
        else:
            pytest.fail("no error reply to an unknown control message")


def test_stream_limit(bundle_dir):
    settings = Settings(bundle_dir=bundle_dir, max_speed=1.0, max_streams=1)
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect("/ws/stream") as first,
    ):
        assert first.receive_json()["type"] == "hello"
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect("/ws/stream") as second,
        ):
            second.receive_json()
        assert refused.value.code == 1013


def test_origin_allow_list(bundle_dir):
    settings = Settings(bundle_dir=bundle_dir, allowed_origins=["https://demo.example"])
    with TestClient(create_app(settings)) as client:
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect(
                "/ws/stream", headers={"origin": "https://evil.example"}
            ) as ws,
        ):
            ws.receive_json()
        assert refused.value.code == 1008
