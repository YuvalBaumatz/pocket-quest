import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest

from imagegencam.quest.companion import ParentBridge, ParentServer
from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style
from imagegencam.quest.jobs import JobState
from imagegencam.quest.runtime import Quest
from imagegencam.quest.storage import Store


@pytest.fixture
def server(tmp_path: Path) -> Iterator[ParentServer]:
    store = Store(tmp_path)
    photo = store.capture(fixture(0), Style.ORIGINAL, None)
    bridge = ParentBridge()
    bridge.publish({"photos": [{"id": photo.id}], "jobs": []}, None)
    instance = ParentServer(bridge, store, port=0)
    instance.start()
    yield instance
    instance.close()


def request(server: ParentServer, path: str, data: object = None, cookie: str = "", **headers: str):
    connection = HTTPConnection("127.0.0.1", server.server.server_port, timeout=6)
    all_headers = {
        "Origin": server.bridge.url,
        "Content-Type": "application/json",
        "Cookie": cookie,
    }
    all_headers.update(headers)
    try:
        connection.request(
            "GET" if data is None else "POST",
            path,
            body=None if data is None else json.dumps(data),
            headers=all_headers,
        )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def pair(server: ParentServer) -> str:
    status, headers, _ = request(server, "/api/pair", {"code": server.bridge.code})
    assert status == 200
    return headers["Set-Cookie"].split(";", 1)[0]


def test_unpaired_browser_cannot_read_photos_state_export_or_change_settings(
    server: ParentServer,
) -> None:
    for path in ("/api/state", "/api/photo/abc", "/api/export"):
        assert request(server, path)[0] == 401
    assert request(server, "/api/action", {"action": "export"})[0] == 401
    assert server.bridge.commands.empty()
    assert request(server, "/")[0] == 200


def test_pairing_is_one_use_private_cookie_and_rotating_revokes_session(
    server: ParentServer,
) -> None:
    old = server.bridge.code
    status, headers, _ = request(server, "/api/pair", {"code": old})
    assert status == 200
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert request(server, "/api/state", cookie=cookie)[0] == 200
    assert request(server, "/api/pair", {"code": old})[0] == 403
    server.rotate_pairing()
    assert request(server, "/api/state", cookie=cookie)[0] == 401


def test_pairing_attempt_limit_and_expiration(server: ParentServer) -> None:
    code = server.bridge.code
    for _ in range(5):
        assert request(server, "/api/pair", {"code": "wrong"})[0] == 403
    assert request(server, "/api/pair", {"code": code})[0] == 403
    server.rotate_pairing()
    server.expires = 0
    assert request(server, "/api/pair", {"code": server.bridge.code})[0] == 403


def test_cross_origin_and_wrong_host_requests_are_rejected(server: ParentServer) -> None:
    cookie = pair(server)
    assert (
        request(
            server, "/api/action", {"action": "export"}, cookie, Origin="http://untrusted.example"
        )[0]
        == 403
    )
    assert request(server, "/api/state", cookie=cookie, Host="untrusted.example")[0] == 403
    assert server.bridge.commands.empty()


def test_authenticated_photo_is_a_decodable_thumbnail_and_path_traversal_fails(
    server: ParentServer,
) -> None:
    cookie = pair(server)
    photo_id = server.bridge.state["photos"][0]["id"]
    status, headers, contents = request(server, f"/api/photo/{photo_id}", cookie=cookie)
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert contents.startswith(b"\x89PNG")
    assert request(server, "/api/photo/../../.env", cookie=cookie)[0] == 404


def test_commands_run_through_bridge_not_request_thread(server: ParentServer) -> None:
    cookie = pair(server)
    result = []
    thread = threading.Thread(
        target=lambda: result.append(
            request(server, "/api/action", {"action": "offline", "value": True}, cookie)
        )
    )
    thread.start()
    command, reply, authorized = server.bridge.commands.get(timeout=2)
    assert authorized()
    assert command == {"action": "offline", "value": True}
    reply.put({"ok": True})
    thread.join(timeout=2)
    assert result[0][0] == 200


@pytest.mark.parametrize("revocation", ["rotate", "expire"])
def test_queued_command_is_reauthorized_before_execution(
    server: ParentServer, revocation: str
) -> None:
    cookie = pair(server)
    result = []
    thread = threading.Thread(
        target=lambda: result.append(
            request(server, "/api/action", {"action": "offline", "value": False}, cookie)
        )
    )
    thread.start()
    queued = server.bridge.commands.get(timeout=2)
    if revocation == "rotate":
        server.rotate_pairing()
    else:
        with server.lock:
            server.sessions = {token: 0 for token in server.sessions}
    server.bridge.commands.put(queued)
    applied = []
    server.bridge.process(applied.append)
    thread.join(timeout=2)
    assert applied == []
    assert result[0][0] == 400


def test_parent_commands_require_consent_and_evidence(tmp_path: Path) -> None:
    store = Store(tmp_path)
    photo = store.capture(fixture(0), Style.CLAY, 4)
    app = Quest(FixtureCamera(), store, start_generation=False)
    app.jobs.enqueue(photo.id, Style.CLAY, "demo", "demo-v1")
    with pytest.raises(ValueError):
        app.parent_command({"action": "approve", "id": photo.id})
    assert app.jobs.all()[0].state == JobState.AWAITING
    app.parent_command({"action": "approve", "id": photo.id, "consent": True})
    app.parent_command({"action": "approve", "id": photo.id, "consent": True})
    assert app.jobs.all()[0].state == JobState.READY
    assert app.jobs.all()[0].attempts == 0
    app.parent_command({"action": "mission", "id": 4})
    app.parent_command({"action": "mission", "id": 4})
    assert app.stamps == {4}
    with pytest.raises(ValueError):
        app.parent_command({"action": "mission", "id": 5})
    with pytest.raises(ValueError):
        app.parent_command({"action": "outing", "missions": [{}]})


def test_companion_never_exposes_credentials_in_state(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    with patch.dict("os.environ", {"GEMINI_API_KEY": "private-test-key"}):
        app.publish_parent_state()
    assert "private-test-key" not in json.dumps(app.parent_bridge.state)
    assert "code" not in app.parent_bridge.state


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "::1", "example.com"])
def test_companion_rejects_ambiguous_or_public_bind_addresses(tmp_path: Path, host: str) -> None:
    with pytest.raises(ValueError):
        ParentServer(ParentBridge(), Store(tmp_path), host=host)
