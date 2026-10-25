import asyncio
import json
import logging
import re
import time
from binascii import Error as BinasciiError
from typing import cast

from botpy import BotAPI, BotHttp, BotWebSocket, Client, ConnectionSession, Token
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot import logger
from astrbot.core.platform.webhook_server import FastAPIWebhookServer

from ..qqofficial.qqofficial_platform_adapter import _ensure_group_message_create_parser

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

_SIGNATURE_HEADER = "X-Signature-Ed25519"
_SIGNATURE_TIMESTAMP_HEADER = "X-Signature-Timestamp"
_BOT_APPID_HEADER = "X-Bot-Appid"
_ED25519_SEED_SIZE = 32
_ED25519_SIGNATURE_SIZE = 64
_SIGNATURE_MAX_SKEW_SECONDS = 300
_EVENT_DEDUP_TTL_SECONDS = 600
_VALIDATION_EVENT_TS_RE = re.compile(r"^\d{10,16}$")
_VALIDATION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_VALIDATION_RATE_LIMIT = 10
_VALIDATION_RATE_WINDOW_SECONDS = 60


def _is_fresh_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.isdigit():
        return False
    timestamp = int(value)
    if len(value) >= 13:
        timestamp //= 1000
    return abs(time.time() - timestamp) <= _SIGNATURE_MAX_SKEW_SECONDS


def _build_ed25519_seed(secret: str) -> bytes:
    if not secret:
        raise ValueError("QQ official bot secret is empty.")

    seed = secret.encode("utf-8")
    while len(seed) < _ED25519_SEED_SIZE:
        seed *= 2
    return seed[:_ED25519_SEED_SIZE]


def _sign_qq_webhook_payload(secret: str, timestamp: str, payload: bytes) -> str:
    seed = _build_ed25519_seed(secret)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    return private_key.sign(timestamp.encode("utf-8") + payload).hex()


def _verify_qq_webhook_signature(
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
) -> bool:
    if not timestamp or not signature:
        return False

    try:
        signature_buffer = bytes.fromhex(signature)
    except BinasciiError, ValueError:
        return False

    if (
        len(signature_buffer) != _ED25519_SIGNATURE_SIZE
        or signature_buffer[63] & 224 != 0
    ):
        return False

    try:
        seed = _build_ed25519_seed(secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        public_key = private_key.public_key()
        public_key.verify(signature_buffer, timestamp.encode("utf-8") + body)
    except InvalidSignature, ValueError:
        return False
    return True


class QQOfficialWebhook:
    def __init__(
        self, config: dict, event_queue: asyncio.Queue, botpy_client: Client
    ) -> None:
        self.appid = config["appid"]
        self.secret = config["secret"]
        self.port = config.get("port", 6196)
        self.is_sandbox = config.get("is_sandbox", False)
        self.callback_server_host = config.get("callback_server_host", "127.0.0.1")

        if isinstance(self.port, str):
            self.port = int(self.port)

        self.http: BotHttp = BotHttp(
            timeout=300,
            is_sandbox=self.is_sandbox,
            app_id=self.appid,
            secret=self.secret,
        )
        self.api: BotAPI = BotAPI(http=self.http)
        self.token = Token(self.appid, self.secret)

        self.server = FastAPIWebhookServer("qq-official-webhook")
        self.server.add_url_rule(
            "/astrbot-qo-webhook/callback",
            view_func=self.callback,
            methods=["POST"],
        )
        self.client = botpy_client
        self.event_queue = event_queue
        self.shutdown_event = asyncio.Event()
        self._connection: ConnectionSession | None = None

        # Cache for extra fields extracted from raw webhook payloads, keyed by message id
        self._extra_data_cache: dict[str, dict] = {}

        # Deduplication cache for webhook retry callbacks.
        self._seen_event_ids: dict[str, float] = {}
        self._dedup_ttl: int = _EVENT_DEDUP_TTL_SECONDS

    async def initialize(self) -> None:
        logger.info("正在登录到 QQ 官方机器人...")
        self.user = await self.http.login(self.token)
        logger.info(f"已登录 QQ 官方机器人账号: {self.user}")
        # 直接注入到 botpy 的 Client，移花接木！
        self.client.api = self.api
        self.client.http = self.http
        self._setup_connection()

    def _setup_connection(self) -> None:
        if self._connection is not None:
            return
        _ensure_group_message_create_parser()
        self.client.api = self.api
        self.client.http = self.http

        async def bot_connect() -> None:
            pass

        self._connection = ConnectionSession(
            max_async=1,
            connect=bot_connect,
            dispatch=self.client.ws_dispatch,
            loop=asyncio.get_running_loop(),
            api=self.api,
        )

    async def webhook_validation(self, validation_payload: dict) -> dict:
        event_ts = validation_payload.get("event_ts")
        plain_token = validation_payload.get("plain_token")
        if not isinstance(event_ts, str) or not _VALIDATION_EVENT_TS_RE.fullmatch(
            event_ts
        ):
            raise ValueError("Invalid validation payload.")
        if not isinstance(plain_token, str) or not _VALIDATION_TOKEN_RE.fullmatch(
            plain_token
        ):
            raise ValueError("Invalid validation payload.")
        if not _is_fresh_timestamp(event_ts):
            raise ValueError("Stale validation payload.")

        return {
            "plain_token": plain_token,
            "signature": _sign_qq_webhook_payload(
                self.secret,
                event_ts,
                plain_token.encode("utf-8"),
            ),
        }

    def _allow_validation_attempt(self) -> bool:
        now = time.monotonic()
        attempts = getattr(self, "_validation_attempts", None)
        if attempts is None:
            attempts = []
            self._validation_attempts = attempts
        cutoff = now - _VALIDATION_RATE_WINDOW_SECONDS
        while attempts and attempts[0] < cutoff:
            attempts.pop(0)
        if len(attempts) >= _VALIDATION_RATE_LIMIT:
            return False
        attempts.append(now)
        return True

    def pop_extra_data(self, message_id: str) -> dict:
        """Pop and return extra fields cached from the raw webhook payload for a given message ID."""
        return self._extra_data_cache.pop(message_id, {})

    async def callback(self, request):
        """内部服务器的回调入口"""
        return await self.handle_callback(request)

    async def handle_callback(self, request) -> dict | tuple[dict[str, str], int]:
        """处理 webhook 回调，可被统一 webhook 入口复用

        Args:
            request: FastAPI webhook request 对象

        Returns:
            响应数据
        """
        body = await request.get_data()
        try:
            msg = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("qq_official_webhook callback body is not valid JSON.")
            return {"error": "Invalid JSON"}, 400
        if not isinstance(msg, dict):
            return {"error": "Invalid JSON"}, 400

        logger.debug(f"收到 qq_official_webhook 回调: {msg}")

        event = msg.get("t")
        opcode = msg.get("op")
        data = msg.get("d")

        if opcode == 13:
            if not isinstance(data, dict):
                return {"error": "Invalid validation payload"}, 400
            appid = request.headers.get(_BOT_APPID_HEADER)
            configured_appid = getattr(self, "appid", None)
            if appid and configured_appid and appid != configured_appid:
                return {"error": "Invalid validation payload"}, 403
            if not self._allow_validation_attempt():
                return {"error": "Too many validation attempts"}, 429
            try:
                signed = await self.webhook_validation(data)
            except TypeError, ValueError:
                logger.warning("qq_official_webhook validation payload is invalid.")
                return {"error": "Invalid validation payload"}, 400
            logger.debug(f"webhook validation response: {signed}")
            return signed

        signature_timestamp = request.headers.get(_SIGNATURE_TIMESTAMP_HEADER) or ""
        if not _is_fresh_timestamp(signature_timestamp):
            logger.warning("qq_official_webhook timestamp is missing or stale.")
            return {"error": "Invalid signature"}, 401
        if not _verify_qq_webhook_signature(
            self.secret,
            signature_timestamp,
            request.headers.get(_SIGNATURE_HEADER),
            body,
        ):
            logger.warning("qq_official_webhook signature verification failed.")
            return {"error": "Invalid signature"}, 401

        event_id = msg.get("id")
        if event_id:
            now = time.monotonic()
            # Lazily evict expired entries to prevent unbounded growth.
            expired = [
                k
                for k, ts in self._seen_event_ids.items()
                if now - ts > self._dedup_ttl
            ]
            for k in expired:
                del self._seen_event_ids[k]
            if event_id in self._seen_event_ids:
                logger.debug(f"Duplicate webhook event {event_id!r}, skipping.")
                return {"opcode": 12}
            self._seen_event_ids[event_id] = now

        if event and opcode == BotWebSocket.WS_DISPATCH_EVENT:
            event = msg["t"].lower()
            if self._connection is None:
                logger.warning(
                    "qq_official_webhook botpy connection is not initialized; "
                    "creating parser connection lazily.",
                )
                self._setup_connection()
            connection = cast(ConnectionSession, self._connection)

            # Extract extra fields from raw payload before botpy parses and discards them
            if data:
                msg_id = data.get("id")
                if msg_id:
                    author = data.get("author") or {}
                    extra: dict = {}
                    if union_openid := author.get("union_openid"):
                        extra["union_openid"] = union_openid
                    if message_scene := data.get("message_scene"):
                        extra["message_scene"] = message_scene
                    if extra:
                        self._extra_data_cache[msg_id] = extra
            try:
                func = connection.parser[event]
            except KeyError:
                logger.error("_parser unknown event %s.", event)
                if data:
                    self._extra_data_cache.pop(data.get("id", ""), None)
            else:
                func(msg)

        return {"opcode": 12}

    async def start_polling(self) -> None:
        logger.info(
            f"将在 {self.callback_server_host}:{self.port} 端口启动 QQ 官方机器人 webhook 适配器。",
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
