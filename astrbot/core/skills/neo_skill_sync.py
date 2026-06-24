from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from astrbot.core.computer.computer_client import sync_skills_to_active_sandboxes
from astrbot.core.skills._neo_skill_sync_utils import (
    MAP_FILE_NAME,
    MAP_VERSION,
    SKILL_NAME_RE,
    NeoSkillSyncResult,
    ensure_skill_frontmatter,
    now_iso,
    to_jsonable,
)
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_skills_path


class NeoSkillSyncManager:
    @staticmethod
    def sync_result_to_dict(result: NeoSkillSyncResult) -> dict[str, str]:
        return {
            "skill_key": result.skill_key,
            "local_skill_name": result.local_skill_name,
            "release_id": result.release_id,
            "candidate_id": result.candidate_id,
            "payload_ref": result.payload_ref,
            "map_path": result.map_path,
            "synced_at": result.synced_at,
        }

    def __init__(
        self,
        *,
        skills_root: str | None = None,
        map_path: str | None = None,
    ) -> None:
        self.skills_root = skills_root or get_astrbot_skills_path()
        self.map_path = map_path or str(Path(self.skills_root) / MAP_FILE_NAME)
        os.makedirs(self.skills_root, exist_ok=True)

    def _load_map(self) -> dict[str, Any]:
        if not os.path.exists(self.map_path):
            return {"version": MAP_VERSION, "items": {}}
        try:
            with open(self.map_path, encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                return {"version": MAP_VERSION, "items": {}}
            items = data.get("items", {})
            if not isinstance(items, dict):
                items = {}
            return {"version": int(data.get("version", MAP_VERSION)), "items": items}
        except Exception:
            return {"version": MAP_VERSION, "items": {}}

    def _save_map(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.map_path), exist_ok=True)
        with open(self.map_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    @staticmethod
    def normalize_skill_name(skill_key: str) -> str:
        normalized = SKILL_NAME_RE.sub("-", skill_key.strip().lower())
        normalized = normalized.strip("._-")
        if not normalized:
            normalized = "skill"
        return f"neo_{normalized}"

    def _resolve_local_skill_name(self, skill_key: str, mapping: dict[str, Any]) -> str:
        items = self._get_mapping_items(mapping)
        existing_name = self._get_existing_local_skill_name(skill_key, items)
        if existing_name is not None:
            return existing_name
        base = self.normalize_skill_name(skill_key)
        used_names = self._get_used_local_skill_names(items)
        if base not in used_names:
            return base
        suffix = hashlib.sha256(skill_key.encode("utf-8")).hexdigest()[:8]
        return f"{base}-{suffix}"

    @staticmethod
    def _get_mapping_items(mapping: dict[str, Any]) -> dict[str, Any]:
        items = mapping.get("items", {})
        return items if isinstance(items, dict) else {}

    @staticmethod
    def _get_existing_local_skill_name(
        skill_key: str,
        items: dict[str, Any],
    ) -> str | None:
        existing = items.get(skill_key)
        if not isinstance(existing, dict):
            return None
        local_name = existing.get("local_skill_name")
        if isinstance(local_name, str) and local_name:
            return local_name
        return None

    @staticmethod
    def _get_used_local_skill_names(items: dict[str, Any]) -> set[str]:
        return {
            str(value.get("local_skill_name"))
            for value in items.values()
            if isinstance(value, dict) and value.get("local_skill_name")
        }

    async def _find_release(self, client: Any, *, release_id: str) -> dict[str, Any]:
        offset = 0
        while True:
            page = await client.skills.list_releases(limit=100, offset=offset)
            page_json = to_jsonable(page)
            items = self._get_release_page_items(page_json)
            matched_item = self._find_release_in_items(items, release_id)
            if matched_item is not None:
                return matched_item
            offset = self._advance_release_offset(offset, items)
            if self._is_last_release_page(page_json, offset, items):
                break
        raise ValueError(f"Release not found: {release_id}")

    @staticmethod
    def _get_release_page_items(page_json: dict[str, Any]) -> list[Any]:
        items = page_json.get("items", [])
        return items if isinstance(items, list) else []

    @staticmethod
    def _advance_release_offset(offset: int, items: list[Any]) -> int:
        return offset + len(items)

    @staticmethod
    def _find_release_in_items(
        items: list[Any],
        release_id: str,
    ) -> dict[str, Any] | None:
        for item in items:
            if isinstance(item, dict) and item.get("id") == release_id:
                return item
        return None

    @staticmethod
    def _is_last_release_page(
        page_json: dict[str, Any],
        offset: int,
        items: list[Any],
    ) -> bool:
        total = int(page_json.get("total", 0) or 0)
        return offset >= total or not items

    async def _find_active_stable_release(
        self,
        client: Any,
        *,
        skill_key: str,
    ) -> dict[str, Any]:
        page = await client.skills.list_releases(
            skill_key=skill_key,
            active_only=True,
            stage="stable",
            limit=1,
            offset=0,
        )
        page_json = to_jsonable(page)
        items = page_json.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError(
                f"No active stable release found for skill_key: {skill_key}"
            )
        if not isinstance(items[0], dict):
            raise ValueError("Unexpected release payload format.")
        return items[0]

    async def _resolve_release_for_sync(
        self,
        client: Any,
        *,
        release_id: str | None,
        skill_key: str | None,
    ) -> dict[str, Any]:
        if release_id:
            return await self._find_release(client, release_id=release_id)
        if skill_key:
            return await self._find_active_stable_release(client, skill_key=skill_key)
        raise ValueError("release_id or skill_key is required for sync.")

    @staticmethod
    def _extract_release_sync_fields(
        release: dict[str, Any],
        *,
        require_stable: bool,
    ) -> tuple[str, str, str]:
        release_id_val = NeoSkillSyncManager._get_required_release_field(
            release,
            "id",
        )
        skill_key_val = NeoSkillSyncManager._get_required_release_field(
            release,
            "skill_key",
        )
        candidate_id = NeoSkillSyncManager._get_required_release_field(
            release,
            "candidate_id",
        )
        release_stage_raw = release.get("stage")
        release_stage_value = getattr(release_stage_raw, "value", release_stage_raw)
        release_stage = str(release_stage_value or "").strip().lower()
        if require_stable and release_stage != "stable":
            raise ValueError(
                "Only stable releases can be synced to local SKILL.md "
                f"(got: {release_stage_raw})."
            )
        return release_id_val, skill_key_val, candidate_id

    @staticmethod
    def _get_required_release_field(release: dict[str, Any], field_name: str) -> str:
        field_value = str(release.get(field_name) or "")
        if not field_value:
            raise ValueError("Release payload is incomplete.")
        return field_value

    async def _get_candidate_payload_ref(self, client: Any, candidate_id: str) -> str:
        candidate = await client.skills.get_candidate(candidate_id)
        candidate_json = to_jsonable(candidate)
        payload_ref = candidate_json.get("payload_ref")
        if not isinstance(payload_ref, str) or not payload_ref:
            raise ValueError("Candidate payload_ref is missing.")
        return payload_ref

    async def _get_skill_markdown(self, client: Any, payload_ref: str) -> str:
        payload_resp = await client.skills.get_payload(payload_ref)
        payload_json = to_jsonable(payload_resp)
        payload = payload_json.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Skill payload must be a JSON object.")
        skill_markdown = payload.get("skill_markdown")
        if not isinstance(skill_markdown, str) or not skill_markdown.strip():
            raise ValueError(
                "payload.skill_markdown is required for stable sync to local skill."
            )
        return skill_markdown

    def _write_synced_skill(
        self,
        *,
        skill_key: str,
        release_id: str,
        candidate_id: str,
        payload_ref: str,
        skill_markdown: str,
    ) -> str:
        mapping = self._load_map()
        local_skill_name = self._resolve_local_skill_name(skill_key, mapping)
        skill_dir = Path(self.skills_root) / local_skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        normalized_markdown = ensure_skill_frontmatter(
            skill_markdown,
            skill_name=local_skill_name,
            skill_key=skill_key,
        )
        (skill_dir / "SKILL.md").write_text(normalized_markdown, encoding="utf-8")
        items = mapping.setdefault("items", {})
        items[skill_key] = {
            "local_skill_name": local_skill_name,
            "latest_release_id": release_id,
            "latest_candidate_id": candidate_id,
            "latest_payload_ref": payload_ref,
            "updated_at": now_iso(),
        }
        mapping["version"] = MAP_VERSION
        self._save_map(mapping)
        return local_skill_name

    async def sync_release(
        self,
        client: Any,
        *,
        release_id: str | None = None,
        skill_key: str | None = None,
        require_stable: bool = True,
    ) -> NeoSkillSyncResult:
        release = await self._resolve_release_for_sync(
            client,
            release_id=release_id,
            skill_key=skill_key,
        )
        release_id_val, skill_key_val, candidate_id = self._extract_release_sync_fields(
            release,
            require_stable=require_stable,
        )
        payload_ref = await self._get_candidate_payload_ref(client, candidate_id)
        skill_markdown = await self._get_skill_markdown(client, payload_ref)
        local_skill_name = self._write_synced_skill(
            skill_key=skill_key_val,
            release_id=release_id_val,
            candidate_id=candidate_id,
            payload_ref=payload_ref,
            skill_markdown=skill_markdown,
        )

        SkillManager().set_skill_active(local_skill_name, True)
        await sync_skills_to_active_sandboxes()

        return NeoSkillSyncResult(
            skill_key=skill_key_val,
            local_skill_name=local_skill_name,
            release_id=release_id_val,
            candidate_id=candidate_id,
            payload_ref=payload_ref,
            map_path=self.map_path,
            synced_at=now_iso(),
        )

    async def promote_with_optional_sync(
        self,
        client: Any,
        *,
        candidate_id: str,
        stage: str,
        sync_to_local: bool,
    ) -> dict[str, Any]:
        release = await client.skills.promote_candidate(candidate_id, stage=stage)
        release_json = to_jsonable(release)

        sync_json: dict[str, Any] | None = None
        rollback_json: dict[str, Any] | None = None
        sync_error: str | None = None

        if self._should_sync_promoted_release(stage, sync_to_local):
            try:
                sync_result = await self.sync_release(
                    client,
                    release_id=str(release_json.get("id", "")),
                    require_stable=True,
                )
                sync_json = self.sync_result_to_dict(sync_result)
            except Exception as err:
                sync_error = str(err)
                rollback_json = await self._rollback_failed_release(
                    client,
                    release_id=str(release_json.get("id", "")),
                    sync_error=sync_error,
                )

        return {
            "release": release_json,
            "sync": sync_json,
            "rollback": rollback_json,
            "sync_error": sync_error,
        }

    @staticmethod
    def _should_sync_promoted_release(stage: str, sync_to_local: bool) -> bool:
        return stage == "stable" and sync_to_local

    async def _rollback_failed_release(
        self,
        client: Any,
        *,
        release_id: str,
        sync_error: str,
    ) -> dict[str, Any]:
        try:
            rollback = await client.skills.rollback_release(release_id)
            return to_jsonable(rollback)
        except Exception as rollback_err:
            rollback_msg = str(rollback_err)
            if "no previous release exists" in rollback_msg.lower():
                return {
                    "skipped": True,
                    "reason": rollback_msg,
                }
            raise RuntimeError(
                "stable release synced failed and auto rollback also failed; "
                f"sync_error={sync_error}; rollback_error={rollback_err}"
            ) from rollback_err
