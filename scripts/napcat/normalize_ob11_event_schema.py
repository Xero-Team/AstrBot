from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FLOAT_FIELD_NAMES = frozenset(
    {
        "timeout",
    }
)

INTEGER_FIELD_NAMES = frozenset(
    {
        "age",
        "busid",
        "cache",
        "count",
        "duration",
        "font",
        "ignore",
        "interval",
        "level",
        "magic",
        "proxy",
        "seq",
        "size",
        "temp_source",
        "time",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize NapCat OB11 event JSON Schema so ID-like and count-like "
            "fields generate as Python integers."
        )
    )
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--output", required=True, type=Path, dest="output_path")
    return parser.parse_args()


def is_integer_enum(schema: dict[str, Any]) -> bool:
    values = schema.get("enum")
    if not isinstance(values, list) or not values:
        return False
    return all(
        isinstance(value, int) and not isinstance(value, bool) for value in values
    )


def should_use_integer_type(property_name: str | None, schema: dict[str, Any]) -> bool:
    if schema.get("type") != "number":
        return False
    if is_integer_enum(schema):
        return True
    if property_name is None or property_name in FLOAT_FIELD_NAMES:
        return False
    return property_name.endswith("_id") or property_name in INTEGER_FIELD_NAMES


def normalize_schema(
    node: dict[str, Any] | list[Any], property_name: str | None = None
) -> int:
    normalized_count = 0

    if isinstance(node, dict):
        if should_use_integer_type(property_name, node):
            node["type"] = "integer"
            normalized_count += 1

        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for child_name, child_node in value.items():
                    if isinstance(child_node, (dict, list)):
                        normalized_count += normalize_schema(child_node, child_name)
                continue

            if key in {"definitions", "$defs", "patternProperties"} and isinstance(
                value, dict
            ):
                for child_node in value.values():
                    if isinstance(child_node, (dict, list)):
                        normalized_count += normalize_schema(child_node)
                continue

            if isinstance(value, dict):
                normalized_count += normalize_schema(value)
                continue

            if isinstance(value, list):
                normalized_count += normalize_schema(value)

        return normalized_count

    for item in node:
        if isinstance(item, (dict, list)):
            normalized_count += normalize_schema(item)

    return normalized_count


def _is_heartbeat_schema(candidate: dict[str, Any]) -> bool:
    properties = candidate.get("properties")
    if not isinstance(properties, dict):
        return False
    meta_event_type = properties.get("meta_event_type")
    if not isinstance(meta_event_type, dict):
        return False
    const = meta_event_type.get("const")
    if const == "heartbeat":
        return True
    enum_values = meta_event_type.get("enum")
    return isinstance(enum_values, list) and "heartbeat" in enum_values


def _fix_heartbeat_schema(raw_schema: dict[str, Any]) -> int:
    defs = raw_schema.get("$defs")
    if not isinstance(defs, dict):
        defs = raw_schema.get("definitions")
    if not isinstance(defs, dict):
        return 0

    heartbeat_schema: dict[str, Any] | None = None

    for candidate in defs.values():
        if not isinstance(candidate, dict):
            continue
        if heartbeat_schema is None and _is_heartbeat_schema(candidate):
            heartbeat_schema = candidate

    if heartbeat_schema is None:
        return 0

    fixed_count = 0

    heartbeat_properties = heartbeat_schema.setdefault("properties", {})
    if not isinstance(heartbeat_properties, dict):
        return 0

    if "interval" not in heartbeat_properties:
        heartbeat_properties["interval"] = {
            "type": "integer",
            "description": "到下次心跳的间隔，单位毫秒",
        }
        fixed_count += 1

    heartbeat_required = heartbeat_schema.setdefault("required", [])
    if isinstance(heartbeat_required, list) and "interval" not in heartbeat_required:
        heartbeat_required.append("interval")
        fixed_count += 1

    status_schema = heartbeat_properties.get("status")
    if not isinstance(status_schema, dict):
        return fixed_count

    status_properties = status_schema.setdefault("properties", {})
    if isinstance(status_properties, dict) and "interval" in status_properties:
        del status_properties["interval"]
        fixed_count += 1
    for name, description in (
        ("online", "Bot是否在线"),
        ("good", "状态是否正常"),
    ):
        if isinstance(status_properties, dict) and name not in status_properties:
            status_properties[name] = {"type": "boolean", "description": description}
            fixed_count += 1

    status_required = status_schema.setdefault("required", [])
    if isinstance(status_required, list):
        while "interval" in status_required:
            status_required.remove("interval")
            fixed_count += 1
        for required_field in ("online", "good"):
            if required_field not in status_required:
                status_required.append(required_field)
                fixed_count += 1

    return fixed_count


def _get_schema_definitions(raw_schema: dict[str, Any]) -> dict[str, Any] | None:
    defs = raw_schema.get("$defs")
    if isinstance(defs, dict):
        return defs
    defs = raw_schema.get("definitions")
    if isinstance(defs, dict):
        return defs
    return None


def _remove_required_fields(schema: dict[str, Any], *field_names: str) -> int:
    required = schema.get("required")
    if not isinstance(required, list):
        return 0

    removed_count = 0
    for field_name in field_names:
        while field_name in required:
            required.remove(field_name)
            removed_count += 1
    return removed_count


def _relax_napcat_message_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    fixed_count = 0

    message_array_schema = {
        "type": "array",
        "items": {"$ref": "#/definitions/OB11Segment"},
        "description": "消息内容",
    }
    message_union_schema = {
        "anyOf": [
            message_array_schema,
            {"type": "string", "description": "消息内容"},
        ],
        "description": "消息内容",
    }

    def _ensure_message_shape(
        message_schema: dict[str, Any],
    ) -> int:
        if message_schema == message_union_schema:
            return 0
        message_schema.clear()
        message_schema.update(message_union_schema)
        return 1

    def _ensure_optional_property(
        properties: dict[str, Any],
        field_name: str,
        schema: dict[str, Any],
    ) -> int:
        if field_name in properties:
            return 0
        properties[field_name] = schema
        return 1

    def _replace_property_schema(
        properties: dict[str, Any],
        field_name: str,
        schema: dict[str, Any],
    ) -> int:
        current = properties.get(field_name)
        if current == schema:
            return 0
        properties[field_name] = schema
        return 1

    friend_sender = defs.get("FriendSender")
    if isinstance(friend_sender, dict):
        fixed_count += _remove_required_fields(friend_sender, "nickname")
        friend_sender_properties = friend_sender.get("properties")
        if (
            isinstance(friend_sender_properties, dict)
            and "card" not in friend_sender_properties
        ):
            friend_sender_properties["card"] = {
                "type": "string",
                "description": "群临时会话中的群名片/备注",
            }
            fixed_count += 1

    group_sender = defs.get("GroupSender")
    if isinstance(group_sender, dict):
        fixed_count += _remove_required_fields(group_sender, "nickname", "role")
        group_sender_properties = group_sender.get("properties")
        if isinstance(group_sender_properties, dict):
            role_schema = group_sender_properties.get("role")
            if isinstance(role_schema, dict) and "enum" in role_schema:
                del role_schema["enum"]
                fixed_count += 1

    private_message = defs.get("OB11PrivateMessage")
    if isinstance(private_message, dict):
        fixed_count += _remove_required_fields(private_message, "sub_type")
        private_properties = private_message.get("properties")
        if isinstance(private_properties, dict):
            message_schema = private_properties.get("message")
            if isinstance(message_schema, dict):
                fixed_count += _ensure_message_shape(message_schema)
            sub_type_schema = private_properties.get("sub_type")
            if isinstance(sub_type_schema, dict):
                if "const" in sub_type_schema:
                    del sub_type_schema["const"]
                    fixed_count += 1
                if "enum" in sub_type_schema:
                    del sub_type_schema["enum"]
                    fixed_count += 1
                if sub_type_schema.get("type") != "string":
                    sub_type_schema["type"] = "string"
                    fixed_count += 1
            for field_name, schema in (
                (
                    "message_format",
                    {"type": "string", "description": "消息格式"},
                ),
                (
                    "message_seq",
                    {"type": "integer", "description": "消息序列号"},
                ),
                ("real_id", {"type": "integer", "description": "真实ID"}),
                (
                    "real_seq",
                    {
                        "anyOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "真实序列号",
                    },
                ),
                (
                    "group_id",
                    {"type": "integer", "description": "群临时会话对应的群号"},
                ),
                (
                    "group_name",
                    {"type": "string", "description": "群临时会话对应的群名称"},
                ),
                (
                    "message_sent_type",
                    {"type": "string", "description": "消息发送类型"},
                ),
                (
                    "target_id",
                    {"type": "integer", "description": "接收者QQ"},
                ),
            ):
                fixed_count += _ensure_optional_property(
                    private_properties, field_name, schema
                )
            fixed_count += _replace_property_schema(
                private_properties,
                "target_id",
                {"type": "integer", "description": "接收者QQ"},
            )

    group_message = defs.get("OB11GroupMessage")
    if isinstance(group_message, dict):
        group_properties = group_message.get("properties")
        if isinstance(group_properties, dict):
            message_schema = group_properties.get("message")
            if isinstance(message_schema, dict):
                fixed_count += _ensure_message_shape(message_schema)
            for field_name, schema in (
                (
                    "message_format",
                    {"type": "string", "description": "消息格式"},
                ),
                (
                    "message_seq",
                    {"type": "integer", "description": "消息序列号"},
                ),
                ("real_id", {"type": "integer", "description": "真实ID"}),
                (
                    "real_seq",
                    {
                        "anyOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "真实序列号",
                    },
                ),
                ("group_name", {"type": "string", "description": "群名称"}),
                (
                    "message_sent_type",
                    {"type": "string", "description": "消息发送类型"},
                ),
            ):
                fixed_count += _ensure_optional_property(
                    group_properties, field_name, schema
                )

    return fixed_count


def _augment_napcat_segment_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    segment_schema = defs.get("OB11Segment")
    if not isinstance(segment_schema, dict):
        return 0

    any_of = segment_schema.get("anyOf")
    if not isinstance(any_of, list):
        return 0

    fixed_count = 0

    extra_segment_definitions: dict[str, dict[str, Any]] = {
        "MFaceSegment": {
            "type": "object",
            "description": "商城表情消息段",
            "additionalProperties": False,
            "properties": {
                "type": {"const": "mface", "type": "string"},
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "emoji_package_id": {
                            "type": "integer",
                            "description": "表情包ID",
                        },
                        "emoji_id": {"type": "string", "description": "表情ID"},
                        "key": {"type": "string", "description": "表情key"},
                        "summary": {"type": "string", "description": "表情摘要"},
                    },
                    "required": [
                        "emoji_package_id",
                        "emoji_id",
                        "key",
                        "summary",
                    ],
                },
            },
            "required": ["type", "data"],
        },
        "MarkdownSegment": {
            "type": "object",
            "description": "Markdown消息段",
            "additionalProperties": False,
            "properties": {
                "type": {"const": "markdown", "type": "string"},
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Markdown内容",
                        }
                    },
                    "required": ["content"],
                },
            },
            "required": ["type", "data"],
        },
        "MiniAppSegment": {
            "type": "object",
            "description": "小程序消息段",
            "additionalProperties": False,
            "properties": {
                "type": {"const": "miniapp", "type": "string"},
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "data": {"type": "string", "description": "小程序数据"}
                    },
                    "required": ["data"],
                },
            },
            "required": ["type", "data"],
        },
        "OnlineFileSegment": {
            "type": "object",
            "description": "在线文件消息段",
            "additionalProperties": False,
            "properties": {
                "type": {"const": "onlinefile", "type": "string"},
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "msgId": {"type": "string", "description": "消息ID"},
                        "elementId": {"type": "string", "description": "元素ID"},
                        "fileName": {"type": "string", "description": "文件名"},
                        "fileSize": {"type": "string", "description": "文件大小"},
                        "isDir": {"type": "boolean", "description": "是否为目录"},
                    },
                    "required": [
                        "msgId",
                        "elementId",
                        "fileName",
                        "fileSize",
                        "isDir",
                    ],
                },
            },
            "required": ["type", "data"],
        },
        "FlashTransferSegment": {
            "type": "object",
            "description": "QQ闪传消息段",
            "additionalProperties": False,
            "properties": {
                "type": {"const": "flashtransfer", "type": "string"},
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fileSetId": {
                            "type": "string",
                            "description": "文件集ID",
                        }
                    },
                    "required": ["fileSetId"],
                },
            },
            "required": ["type", "data"],
        },
    }

    existing_refs = {
        item.get("$ref")
        for item in any_of
        if isinstance(item, dict) and isinstance(item.get("$ref"), str)
    }

    for definition_name, definition_schema in extra_segment_definitions.items():
        if definition_name not in defs:
            defs[definition_name] = definition_schema
            fixed_count += 1
        ref = f"#/definitions/{definition_name}"
        if ref not in existing_refs:
            any_of.append({"$ref": ref})
            existing_refs.add(ref)
            fixed_count += 1

    return fixed_count


def _align_napcat_file_like_segment_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    fixed_count = 0

    image_segment = defs.get("ImageSegment")
    if isinstance(image_segment, dict):
        image_properties = image_segment.get("properties")
        if isinstance(image_properties, dict):
            data_schema = image_properties.get("data")
            if isinstance(data_schema, dict):
                data_properties = data_schema.get("properties")
                if isinstance(data_properties, dict):
                    if "summary" not in data_properties:
                        data_properties["summary"] = {
                            "type": "string",
                            "description": "图片摘要",
                        }
                        fixed_count += 1

                    if "sub_type" not in data_properties:
                        data_properties["sub_type"] = {
                            "anyOf": [{"type": "integer"}, {"type": "string"}],
                            "description": "图片子类型",
                        }
                        fixed_count += 1

                    if "file_size" not in data_properties:
                        data_properties["file_size"] = {
                            "anyOf": [{"type": "integer"}, {"type": "string"}],
                            "description": "图片文件大小",
                        }
                        fixed_count += 1

    record_segment = defs.get("RecordSegment")
    if isinstance(record_segment, dict):
        record_properties = record_segment.get("properties")
        if isinstance(record_properties, dict):
            data_schema = record_properties.get("data")
            if isinstance(data_schema, dict):
                data_properties = data_schema.get("properties")
                if isinstance(data_properties, dict):
                    if "path" not in data_properties:
                        data_properties["path"] = {
                            "type": "string",
                            "description": "语音文件路径",
                        }
                        fixed_count += 1

                    if "file_size" not in data_properties:
                        data_properties["file_size"] = {
                            "anyOf": [{"type": "integer"}, {"type": "string"}],
                            "description": "语音文件大小",
                        }
                        fixed_count += 1

    video_segment = defs.get("VideoSegment")
    if isinstance(video_segment, dict):
        video_properties = video_segment.get("properties")
        if isinstance(video_properties, dict):
            data_schema = video_properties.get("data")
            if isinstance(data_schema, dict):
                data_properties = data_schema.get("properties")
                if (
                    isinstance(data_properties, dict)
                    and "file_size" not in data_properties
                ):
                    data_properties["file_size"] = {
                        "anyOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "视频文件大小",
                    }
                    fixed_count += 1

    file_segment = defs.get("FileSegment")
    if isinstance(file_segment, dict):
        file_properties = file_segment.get("properties")
        if isinstance(file_properties, dict):
            data_schema = file_properties.get("data")
            if isinstance(data_schema, dict):
                data_properties = data_schema.get("properties")
                if isinstance(data_properties, dict):
                    if "file_id" not in data_properties:
                        data_properties["file_id"] = {
                            "type": "string",
                            "description": "文件ID",
                        }
                        fixed_count += 1

                    if "file_size" not in data_properties:
                        data_properties["file_size"] = {
                            "anyOf": [{"type": "integer"}, {"type": "string"}],
                            "description": "文件大小",
                        }
                        fixed_count += 1

                    if "url" not in data_properties:
                        data_properties["url"] = {
                            "type": "string",
                            "description": "文件URL",
                        }
                        fixed_count += 1

    return fixed_count


def _align_napcat_custom_music_segment_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    custom_music_segment = defs.get("CustomMusicSegment")
    if not isinstance(custom_music_segment, dict):
        return 0

    segment_properties = custom_music_segment.get("properties")
    if not isinstance(segment_properties, dict):
        return 0

    data_schema = segment_properties.get("data")
    if not isinstance(data_schema, dict):
        return 0

    data_properties = data_schema.get("properties")
    if not isinstance(data_properties, dict):
        return 0

    fixed_count = 0
    required = data_schema.get("required")
    if isinstance(required, list):
        for field_name in ("audio", "title"):
            while field_name in required:
                required.remove(field_name)
                fixed_count += 1
        if "image" not in required:
            required.append("image")
            fixed_count += 1

    for field_name in ("audio", "title", "image"):
        field_schema = data_properties.get(field_name)
        if isinstance(field_schema, dict) and field_schema.get("type") != "string":
            field_schema["type"] = "string"
            fixed_count += 1

    return fixed_count


def _align_napcat_poke_notice_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    poke_schema = defs.get("OneBot11Poke")
    if not isinstance(poke_schema, dict):
        return 0

    properties = poke_schema.get("properties")
    if not isinstance(properties, dict):
        return 0

    fixed_count = 0
    sender_id_schema = {"type": "integer", "description": "消息发送者"}
    if properties.get("sender_id") != sender_id_schema:
        properties["sender_id"] = sender_id_schema
        fixed_count += 1

    raw_info_schema = {"description": "原始戳一戳信息"}
    if properties.get("raw_info") != raw_info_schema:
        properties["raw_info"] = raw_info_schema
        fixed_count += 1

    fixed_count += _remove_required_fields(poke_schema, "sender_id", "raw_info")
    return fixed_count


def _align_napcat_group_reaction_notice_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    reaction_schema = defs.get("OneBot11GroupMessageReaction")
    if not isinstance(reaction_schema, dict):
        return 0

    properties = reaction_schema.get("properties")
    if not isinstance(properties, dict):
        return 0

    fixed_count = 0
    is_add_schema = {"type": "boolean", "description": "是否新增表情回应"}
    if properties.get("is_add") != is_add_schema:
        properties["is_add"] = is_add_schema
        fixed_count += 1

    fixed_count += _remove_required_fields(reaction_schema, "is_add")
    return fixed_count


def _relax_napcat_request_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    group_request = defs.get("OneBot11GroupRequest")
    if not isinstance(group_request, dict):
        return 0

    properties = group_request.get("properties")
    if not isinstance(properties, dict):
        return 0

    sub_type_schema = properties.get("sub_type")
    if not isinstance(sub_type_schema, dict):
        return 0

    fixed_count = 0
    if "const" in sub_type_schema:
        del sub_type_schema["const"]
        fixed_count += 1
    if "enum" in sub_type_schema:
        del sub_type_schema["enum"]
        fixed_count += 1
    if sub_type_schema.get("type") != "string":
        sub_type_schema["type"] = "string"
        fixed_count += 1
    return fixed_count


def _augment_napcat_notice_event_schema(raw_schema: dict[str, Any]) -> int:
    defs = _get_schema_definitions(raw_schema)
    if not isinstance(defs, dict):
        return 0

    all_event_schema = defs.get("OB11AllEvent")
    if not isinstance(all_event_schema, dict):
        return 0

    top_any_of = all_event_schema.get("anyOf")
    if not isinstance(top_any_of, list):
        return 0

    fixed_count = 0

    extra_notice_definitions: dict[str, dict[str, Any]] = {
        "OneBot11BotOffline": {
            "type": "object",
            "description": "Bot离线事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "bot_offline",
                    "type": "string",
                    "description": "通知类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "user_id": {"type": "integer", "description": "机器人 QQ 号"},
                "tag": {"type": "string", "description": "事件标签"},
                "message": {"type": "string", "description": "事件描述"},
            },
            "required": [
                "post_type",
                "notice_type",
                "self_id",
                "time",
                "user_id",
                "tag",
                "message",
            ],
        },
        "OneBot11GroupGrayTip": {
            "type": "object",
            "description": "群灰条消息事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "notify",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {
                    "const": "gray_tip",
                    "type": "string",
                    "description": "提示类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "group_id": {"type": "integer", "description": "群号"},
                "user_id": {"type": "integer", "description": "发送者 QQ 号"},
                "message_id": {"type": "integer", "description": "消息 ID"},
                "busi_id": {"type": "string", "description": "业务 ID"},
                "content": {"type": "string", "description": "灰条内容"},
                "raw_info": {},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "group_id",
                "user_id",
                "message_id",
                "busi_id",
                "content",
                "raw_info",
            ],
        },
        "OneBot11GroupName": {
            "type": "object",
            "description": "群名变更事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "notify",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {
                    "const": "group_name",
                    "type": "string",
                    "description": "提示类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "group_id": {"type": "integer", "description": "群号"},
                "user_id": {"type": "integer", "description": "发送者 QQ 号"},
                "name_new": {"type": "string", "description": "新群名"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "group_id",
                "user_id",
                "name_new",
            ],
        },
        "OneBot11GroupTitle": {
            "type": "object",
            "description": "群头衔变更事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "notify",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {
                    "const": "title",
                    "type": "string",
                    "description": "提示类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "group_id": {"type": "integer", "description": "群号"},
                "user_id": {"type": "integer", "description": "发送者 QQ 号"},
                "title": {"type": "string", "description": "头衔"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "group_id",
                "user_id",
                "title",
            ],
        },
        "OneBot11InputStatus": {
            "type": "object",
            "description": "输入状态事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "notify",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {
                    "const": "input_status",
                    "type": "string",
                    "description": "提示类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "user_id": {"type": "integer", "description": "用户 QQ 号"},
                "group_id": {"type": "integer", "description": "群号"},
                "event_type": {"type": "integer", "description": "事件类型值"},
                "status_text": {"type": "string", "description": "状态文本"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "user_id",
                "group_id",
                "event_type",
                "status_text",
            ],
        },
        "OneBot11ProfileLike": {
            "type": "object",
            "description": "资料卡点赞事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "notify",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {
                    "const": "profile_like",
                    "type": "string",
                    "description": "提示类型",
                },
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "operator_id": {"type": "integer", "description": "操作者 QQ 号"},
                "operator_nick": {"type": "string", "description": "操作者昵称"},
                "times": {"type": "integer", "description": "次数"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "operator_id",
                "operator_nick",
                "times",
            ],
        },
        "OneBot11OnlineFileReceive": {
            "type": "object",
            "description": "在线文件接收侧事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "online_file_receive",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {"type": "string", "description": "提示类型"},
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "peer_id": {"type": "integer", "description": "对端 QQ 号"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "peer_id",
            ],
        },
        "OneBot11OnlineFileSend": {
            "type": "object",
            "description": "在线文件发送侧事件",
            "additionalProperties": False,
            "properties": {
                "post_type": {
                    "const": "notice",
                    "type": "string",
                    "description": "事件类型",
                },
                "notice_type": {
                    "const": "online_file_send",
                    "type": "string",
                    "description": "通知类型",
                },
                "sub_type": {"type": "string", "description": "提示类型"},
                "self_id": {"type": "integer", "description": "收到事件的机器人 QQ 号"},
                "time": {"type": "integer", "description": "事件发生的时间戳"},
                "peer_id": {"type": "integer", "description": "对端 QQ 号"},
            },
            "required": [
                "post_type",
                "notice_type",
                "sub_type",
                "self_id",
                "time",
                "peer_id",
            ],
        },
    }

    existing_refs = {
        item.get("$ref")
        for item in top_any_of
        if isinstance(item, dict) and isinstance(item.get("$ref"), str)
    }

    for definition_name, definition_schema in extra_notice_definitions.items():
        if definition_name not in defs:
            defs[definition_name] = definition_schema
            fixed_count += 1
        ref = f"#/definitions/{definition_name}"
        if ref not in existing_refs:
            top_any_of.append({"$ref": ref})
            existing_refs.add(ref)
            fixed_count += 1

    return fixed_count


def main() -> None:
    args = parse_args()
    raw_schema = json.loads(args.input_path.read_text(encoding="utf-8"))
    normalized_count = normalize_schema(raw_schema)
    normalized_count += _fix_heartbeat_schema(raw_schema)
    normalized_count += _relax_napcat_message_schema(raw_schema)
    normalized_count += _augment_napcat_segment_schema(raw_schema)
    normalized_count += _align_napcat_file_like_segment_schema(raw_schema)
    normalized_count += _align_napcat_custom_music_segment_schema(raw_schema)
    normalized_count += _align_napcat_poke_notice_schema(raw_schema)
    normalized_count += _align_napcat_group_reaction_notice_schema(raw_schema)
    normalized_count += _relax_napcat_request_schema(raw_schema)
    normalized_count += _augment_napcat_notice_event_schema(raw_schema)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(raw_schema, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    print(f"Normalized numeric fields: {normalized_count}")
    print(f"Normalized schema: {args.output_path}")


if __name__ == "__main__":
    main()
