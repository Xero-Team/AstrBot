from astrbot.dashboard.api.webchat import websocket_auth_from_protocols


def test_websocket_auth_reads_token_from_subprotocol_header():
    assert websocket_auth_from_protocols("astrbot, jwt-token") == (
        "jwt-token",
        "astrbot",
    )


def test_websocket_auth_accepts_registered_protocol_without_token():
    assert websocket_auth_from_protocols("astrbot") == (None, "astrbot")


def test_websocket_auth_ignores_empty_header():
    assert websocket_auth_from_protocols(None) == (None, None)
    assert websocket_auth_from_protocols("  ,  ") == (None, None)
