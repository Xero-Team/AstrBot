import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

import aiohttp
import pydantic

from astrbot import logger

from .kook_types import KookApiPaths, KookUserViewResponse

USER_VIEW_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=1)
ROLES_CACHE_MAX_SIZE = 2000
MAX_RETRY_TIMES = 3
RETRY_INTERVAL_SECOND = 1 * 60
ROLE_LOOKUP_WAIT_TIMEOUT_SECONDS = 0.35
SLOW_ROLE_LOOKUP_LOG_THRESHOLD_SECONDS = 0.2


@dataclass
class RolesCache:
    value: set[int] | None = None
    failed_count: int = 0
    latest_update_time: float = 0

    def update(self, roles: set[int] | None) -> None:
        if roles is not None:
            self.failed_count = 0
        self.value = roles
        self.latest_update_time = time.time()

    def add_failed(self):
        self.failed_count += 1

    def reset(self, without_value=False):
        if not without_value:
            self.value = None
        self.failed_count = 0
        self.latest_update_time = 0


class KookRolesRecord:
    """自动和缓存获取机器人所需响应的消息频道的role信息"""

    def __init__(self, bot_id: str, http_client: aiohttp.ClientSession):
        # self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()
        self._bot_id = bot_id
        self._http_client = http_client
        # TODO 这个些配置后续加到适配器配置项里
        self._cache_max_size = ROLES_CACHE_MAX_SIZE
        self._max_retry_times = MAX_RETRY_TIMES
        self._retry_interval = RETRY_INTERVAL_SECOND
        self._roles_cache: OrderedDict[int, RolesCache] = OrderedDict()
        self._pending_tasks: dict[int, asyncio.Future[set[int] | None]] = {}
        self._fetch_tasks: dict[int, asyncio.Task[None]] = {}

    def set_bot_id(self, bot_id: str):
        self._bot_id = bot_id

    def clear_guild_roles_cache(self, guild_id: int):
        self._roles_cache.pop(guild_id, None)
        pending_task = self._fetch_tasks.pop(guild_id, None)
        if pending_task is not None:
            pending_task.cancel()
        self._pending_tasks.pop(guild_id, None)

    async def _fetch_roles_by_guild_id(self, guild_id: int) -> set[int] | None:
        # 由于需要判断bot账号是属于某个角色(role)才会回复消息,
        # 而后续来自同一个频道的消息,在第一次查这个role的时候,
        # 会一直阻塞消息接收直到请求完成或者报错,
        # 所以,这里特意调低了timeout时间,避免阻塞太久
        url = KookApiPaths.USER_VIEW
        try:
            async with self._http_client.get(
                url,
                params={
                    "guild_id": guild_id,
                    "user_id": self._bot_id,
                },
                # TODO 这个超时时间后续加到适配器配置项里
                timeout=USER_VIEW_REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败，状态码: {resp.status} , {await resp.text()}'
                    )
                    return
                try:
                    resp_content = KookUserViewResponse.from_dict(await resp.json())
                except pydantic.ValidationError as e:
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败, 响应数据格式错误: \n{e}'
                    )
                    logger.error(f"[KOOK] 响应内容: {await resp.text()}")
                    return

                if not resp_content.success():
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败: {resp_content.model_dump_json()}'
                    )
                    return

                logger.info(f'[KOOK] 获取机器人在频道"{guild_id}"的角色id成功')
                return set(resp_content.data.roles)

        except Exception as e:
            logger.error(
                f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息时请求异常: {e}'
            )
            return

    def _should_back_off(self, guild_id: int) -> bool:
        cache = self._roles_cache.get(guild_id)
        return bool(
            cache is not None
            and cache.failed_count > self._max_retry_times
            and time.time() - cache.latest_update_time < self._retry_interval
        )

    def prefetch_guild_roles(self, guild_id: int) -> None:
        if (cache := self._roles_cache.get(guild_id)) is not None:
            self._roles_cache.move_to_end(guild_id)
            if cache.value is not None:
                return

        if guild_id in self._pending_tasks:
            return

        if self._should_back_off(guild_id):
            return

        if len(self._roles_cache) + 1 > self._cache_max_size:
            self._roles_cache.popitem(last=False)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[set[int] | None] = loop.create_future()
        task = asyncio.create_task(
            self._refresh_guild_roles(guild_id, future),
            name=f"kook_roles_prefetch_{guild_id}",
        )
        self._pending_tasks[guild_id] = future
        self._fetch_tasks[guild_id] = task
        task.add_done_callback(
            lambda done_task, guild_id=guild_id: self._on_fetch_task_done(
                guild_id, done_task
            )
        )

    async def _refresh_guild_roles(
        self,
        guild_id: int,
        future: asyncio.Future[set[int] | None],
    ) -> None:
        try:
            roles_set = await self._fetch_roles_by_guild_id(guild_id)

            cache = self._roles_cache.get(guild_id)
            if cache is not None:
                cache.update(roles_set)
                self._roles_cache.move_to_end(guild_id)
            else:
                cache = RolesCache(roles_set, latest_update_time=time.time())
                self._roles_cache[guild_id] = cache

            if roles_set is None:
                cache.add_failed()

            if not future.done():
                future.set_result(roles_set)
        except asyncio.CancelledError:
            if not future.done():
                future.cancel()
            raise
        except Exception as e:
            if not future.done():
                future.set_result(None)
            logger.error(
                f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息时发生异常: {e}'
            )

    def _on_fetch_task_done(
        self,
        guild_id: int,
        task: asyncio.Task[None],
    ) -> None:
        self._fetch_tasks.pop(guild_id, None)
        self._pending_tasks.pop(guild_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f'[KOOK] 刷新频道"{guild_id}"角色缓存任务失败: {exc}')

    async def has_role_in_channel(
        self,
        role_id: int,
        guild_id: int,
        *,
        wait_timeout: float = ROLE_LOOKUP_WAIT_TIMEOUT_SECONDS,
    ) -> bool:
        started_at = time.monotonic()
        if (cache := self._roles_cache.get(guild_id)) is not None:
            self._roles_cache.move_to_end(guild_id)
            roles = cache.value
            if roles is not None:
                return role_id in roles

        self.prefetch_guild_roles(guild_id)
        pending = self._pending_tasks.get(guild_id)
        if pending is None:
            return False

        try:
            if wait_timeout <= 0:
                roles = await asyncio.shield(pending)
            else:
                roles = await asyncio.wait_for(
                    asyncio.shield(pending),
                    timeout=wait_timeout,
                )
        except TimeoutError:
            logger.info(
                '[KOOK] 频道"%s"角色缓存查询超时(%.2fs)，本条消息跳过 role mention 命中判定，等待后台缓存补齐。',
                guild_id,
                wait_timeout,
            )
            return False

        elapsed = time.monotonic() - started_at
        if elapsed >= SLOW_ROLE_LOOKUP_LOG_THRESHOLD_SECONDS:
            logger.info(
                '[KOOK] 频道"%s"角色缓存命中耗时 %.2fs',
                guild_id,
                elapsed,
            )
        if roles is None:
            return False
        return role_id in roles
