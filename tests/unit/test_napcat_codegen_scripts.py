import importlib
import importlib.util
import json
from pathlib import Path


def _load_module(module_name: str, relative_path: str):
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_ob11_event_schema_converts_integer_like_numeric_fields():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "number"},
            "timeout": {"type": "number"},
            "count": {"type": "number"},
            "ratio": {"type": "number"},
            "nested": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "number"},
                    "duration": {"type": "number"},
                },
            },
            "variants": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "group_id": {"type": "number"},
                        },
                    }
                ]
            },
            "enum_like": {"type": "number", "enum": [1, 2, 3]},
        },
    }

    normalized_count = module.normalize_schema(schema)

    assert normalized_count == 6
    assert schema["properties"]["user_id"]["type"] == "integer"
    assert schema["properties"]["count"]["type"] == "integer"
    assert schema["properties"]["nested"]["properties"]["message_id"]["type"] == (
        "integer"
    )
    assert schema["properties"]["nested"]["properties"]["duration"]["type"] == (
        "integer"
    )
    assert (
        schema["properties"]["variants"]["anyOf"][0]["properties"]["group_id"]["type"]
        == "integer"
    )
    assert schema["properties"]["enum_like"]["type"] == "integer"
    assert schema["properties"]["timeout"]["type"] == "number"
    assert schema["properties"]["ratio"]["type"] == "number"


def test_normalize_ob11_event_schema_walks_defs_and_pattern_properties():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "Sender": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "number"},
                    "timeout": {"type": "number"},
                },
            }
        },
        "patternProperties": {
            "^x-": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "number"},
                },
            }
        },
    }

    normalized_count = module.normalize_schema(schema)

    assert normalized_count == 2
    assert schema["$defs"]["Sender"]["properties"]["user_id"]["type"] == "integer"
    assert schema["$defs"]["Sender"]["properties"]["timeout"]["type"] == "number"
    assert schema["patternProperties"]["^x-"]["properties"]["group_id"]["type"] == (
        "integer"
    )


def test_normalize_ob11_event_schema_main_writes_normalized_json(
    tmp_path, monkeypatch, capsys
):
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "user_id": {"type": "number"},
                    "timeout": {"type": "number"},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "normalize_ob11_event_schema.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    module.main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    stdout = capsys.readouterr().out

    assert payload["properties"]["user_id"]["type"] == "integer"
    assert payload["properties"]["timeout"]["type"] == "number"
    assert "Normalized numeric fields: 1" in stdout
    assert str(output_path) in stdout


def test_normalize_ob11_event_schema_fixes_heartbeat_shape():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OneBot11Heartbeat": {
                "type": "object",
                "properties": {
                    "post_type": {"const": "meta_event", "type": "string"},
                    "meta_event_type": {"const": "heartbeat", "type": "string"},
                    "status": {
                        "type": "object",
                        "description": "状态信息",
                        "properties": {
                            "interval": {"type": "number"},
                        },
                        "required": ["interval"],
                    },
                },
                "required": ["post_type", "meta_event_type", "status"],
            }
        }
    }

    fixed_count = module._fix_heartbeat_schema(schema)
    heartbeat = schema["$defs"]["OneBot11Heartbeat"]
    status = heartbeat["properties"]["status"]

    assert fixed_count == 8
    assert heartbeat["properties"]["interval"] == {
        "type": "integer",
        "description": "到下次心跳的间隔，单位毫秒",
    }
    assert "interval" in heartbeat["required"]
    assert "interval" not in status["properties"]
    assert status["properties"]["online"]["type"] == "boolean"
    assert status["properties"]["good"]["type"] == "boolean"
    assert status["required"] == ["online", "good"]


def test_normalize_ob11_event_schema_relaxes_napcat_message_sender_and_private_sub_type():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "FriendSender": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string"},
                    "user_id": {"type": "integer"},
                },
                "required": ["nickname", "user_id"],
            },
            "GroupSender": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string"},
                    "role": {"type": "string", "enum": ["admin", "member", "owner"]},
                    "user_id": {"type": "integer"},
                },
                "required": ["nickname", "role", "user_id"],
            },
            "OB11PrivateMessage": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/OB11Segment"},
                    },
                    "sub_type": {"type": "string", "const": "friend"},
                },
                "required": ["sub_type", "message"],
            },
            "OB11GroupMessage": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/OB11Segment"},
                    },
                },
            },
        }
    }

    fixed_count = module._relax_napcat_message_schema(schema)

    assert fixed_count == 23
    assert schema["$defs"]["FriendSender"]["required"] == ["user_id"]
    assert schema["$defs"]["FriendSender"]["properties"]["card"]["type"] == "string"
    assert schema["$defs"]["GroupSender"]["required"] == ["user_id"]
    assert "enum" not in schema["$defs"]["GroupSender"]["properties"]["role"]
    assert schema["$defs"]["OB11PrivateMessage"]["required"] == ["message"]
    assert (
        "const" not in schema["$defs"]["OB11PrivateMessage"]["properties"]["sub_type"]
    )
    assert (
        schema["$defs"]["OB11PrivateMessage"]["properties"]["sub_type"]["type"]
        == "string"
    )
    assert "anyOf" in schema["$defs"]["OB11PrivateMessage"]["properties"]["message"]
    assert (
        schema["$defs"]["OB11PrivateMessage"]["properties"]["message_format"]["type"]
        == "string"
    )
    assert (
        schema["$defs"]["OB11PrivateMessage"]["properties"]["message_seq"]["type"]
        == "integer"
    )
    assert (
        schema["$defs"]["OB11PrivateMessage"]["properties"]["real_id"]["type"]
        == "integer"
    )
    assert "anyOf" in schema["$defs"]["OB11PrivateMessage"]["properties"]["real_seq"]
    assert schema["$defs"]["OB11PrivateMessage"]["properties"]["group_id"]["type"] == (
        "integer"
    )
    assert schema["$defs"]["OB11PrivateMessage"]["properties"]["group_name"][
        "type"
    ] == ("string")
    assert (
        schema["$defs"]["OB11PrivateMessage"]["properties"]["message_sent_type"]["type"]
        == "string"
    )
    assert schema["$defs"]["OB11PrivateMessage"]["properties"]["target_id"]["type"] == (
        "integer"
    )
    assert "anyOf" in schema["$defs"]["OB11GroupMessage"]["properties"]["message"]
    assert (
        schema["$defs"]["OB11GroupMessage"]["properties"]["message_format"]["type"]
        == "string"
    )
    assert (
        schema["$defs"]["OB11GroupMessage"]["properties"]["message_seq"]["type"]
        == "integer"
    )
    assert schema["$defs"]["OB11GroupMessage"]["properties"]["real_id"]["type"] == (
        "integer"
    )
    assert "anyOf" in schema["$defs"]["OB11GroupMessage"]["properties"]["real_seq"]
    assert schema["$defs"]["OB11GroupMessage"]["properties"]["group_name"]["type"] == (
        "string"
    )
    assert (
        schema["$defs"]["OB11GroupMessage"]["properties"]["message_sent_type"]["type"]
        == "string"
    )


def test_normalize_ob11_event_schema_rewrites_napcat_target_id_description():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OB11PrivateMessage": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/OB11Segment"},
                    },
                    "target_id": {
                        "type": "integer",
                        "description": "接收者QQ gocq-http拓展",
                    },
                },
                "required": ["message"],
            }
        }
    }

    fixed_count = module._relax_napcat_message_schema(schema)

    assert fixed_count >= 1
    assert schema["$defs"]["OB11PrivateMessage"]["properties"]["target_id"] == {
        "type": "integer",
        "description": "接收者QQ",
    }


def test_normalize_ob11_event_schema_augments_napcat_nonstandard_segments():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OB11Segment": {
                "anyOf": [
                    {"$ref": "#/definitions/TextSegment"},
                ]
            }
        }
    }

    fixed_count = module._augment_napcat_segment_schema(schema)

    assert fixed_count == 10
    refs = {
        item["$ref"]
        for item in schema["$defs"]["OB11Segment"]["anyOf"]
        if isinstance(item, dict) and "$ref" in item
    }
    assert "#/definitions/MFaceSegment" in refs
    assert "#/definitions/MarkdownSegment" in refs
    assert "#/definitions/MiniAppSegment" in refs
    assert "#/definitions/OnlineFileSegment" in refs
    assert "#/definitions/FlashTransferSegment" in refs
    assert schema["$defs"]["MFaceSegment"]["properties"]["type"]["const"] == "mface"
    assert (
        schema["$defs"]["FlashTransferSegment"]["properties"]["data"]["properties"][
            "fileSetId"
        ]["type"]
        == "string"
    )


def test_normalize_ob11_event_schema_aligns_napcat_real_file_like_segment_fields():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "ImageSegment": {
                "type": "object",
                "properties": {
                    "type": {"const": "image", "type": "string"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "url": {"type": "string"},
                        },
                    },
                },
            },
            "RecordSegment": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "url": {"type": "string"},
                        },
                    },
                },
            },
            "VideoSegment": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "url": {"type": "string"},
                        },
                    },
                },
            },
            "FileSegment": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                        },
                    },
                },
            },
        }
    }

    fixed_count = module._align_napcat_file_like_segment_schema(schema)

    assert fixed_count == 9
    image_properties = schema["$defs"]["ImageSegment"]["properties"]["data"][
        "properties"
    ]
    assert image_properties["summary"]["type"] == "string"
    assert image_properties["sub_type"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    assert image_properties["file_size"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    record_properties = schema["$defs"]["RecordSegment"]["properties"]["data"][
        "properties"
    ]
    assert record_properties["path"]["type"] == "string"
    assert record_properties["file_size"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    video_properties = schema["$defs"]["VideoSegment"]["properties"]["data"][
        "properties"
    ]
    assert video_properties["file_size"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    file_properties = schema["$defs"]["FileSegment"]["properties"]["data"]["properties"]
    assert file_properties["file_id"]["type"] == "string"
    assert file_properties["file_size"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    assert file_properties["url"]["type"] == "string"


def test_normalize_ob11_event_schema_aligns_custom_music_optional_fields():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "CustomMusicSegment": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            "audio": {"type": "string"},
                            "title": {"type": "string"},
                            "image": {"type": "string"},
                            "type": {"const": "custom", "type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["audio", "title", "type", "url"],
                    }
                },
            }
        },
    }

    fixed_count = module._align_napcat_custom_music_segment_schema(schema)

    assert fixed_count == 3
    assert schema["$defs"]["CustomMusicSegment"]["properties"]["data"]["required"] == [
        "type",
        "url",
        "image",
    ]


def test_normalize_ob11_event_schema_aligns_poke_notice_extra_fields():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OneBot11Poke": {
                "type": "object",
                "properties": {
                    "post_type": {"const": "notice", "type": "string"},
                    "notice_type": {"const": "notify", "type": "string"},
                    "sub_type": {"const": "poke", "type": "string"},
                    "self_id": {"type": "integer"},
                    "time": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "target_id": {"type": "integer"},
                },
                "required": [
                    "post_type",
                    "notice_type",
                    "sub_type",
                    "self_id",
                    "time",
                    "user_id",
                    "target_id",
                ],
            }
        },
    }

    fixed_count = module._align_napcat_poke_notice_schema(schema)

    assert fixed_count == 2
    assert schema["$defs"]["OneBot11Poke"]["properties"]["sender_id"] == {
        "type": "integer",
        "description": "消息发送者",
    }
    assert schema["$defs"]["OneBot11Poke"]["properties"]["raw_info"] == {
        "description": "原始戳一戳信息",
    }
    assert "sender_id" not in schema["$defs"]["OneBot11Poke"]["required"]
    assert "raw_info" not in schema["$defs"]["OneBot11Poke"]["required"]


def test_normalize_ob11_event_schema_aligns_group_reaction_notice_extra_fields():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OneBot11GroupMessageReaction": {
                "type": "object",
                "properties": {
                    "post_type": {"const": "notice", "type": "string"},
                    "notice_type": {
                        "const": "group_msg_emoji_like",
                        "type": "string",
                    },
                    "self_id": {"type": "integer"},
                    "time": {"type": "integer"},
                    "group_id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "message_id": {"type": "integer"},
                    "likes": {"type": "array"},
                },
                "required": [
                    "post_type",
                    "notice_type",
                    "self_id",
                    "time",
                    "group_id",
                    "user_id",
                    "message_id",
                    "likes",
                ],
            }
        },
    }

    fixed_count = module._align_napcat_group_reaction_notice_schema(schema)

    assert fixed_count == 1
    assert schema["$defs"]["OneBot11GroupMessageReaction"]["properties"]["is_add"] == {
        "type": "boolean",
        "description": "是否新增表情回应",
    }
    assert "is_add" not in schema["$defs"]["OneBot11GroupMessageReaction"]["required"]


def test_normalize_ob11_event_schema_relaxes_group_request_sub_type_to_string():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OneBot11GroupRequest": {
                "type": "object",
                "properties": {
                    "sub_type": {
                        "enum": ["add", "invite"],
                        "description": "请求子类型",
                    }
                },
                "required": ["sub_type"],
            }
        }
    }

    fixed_count = module._relax_napcat_request_schema(schema)

    assert fixed_count == 2
    assert schema["$defs"]["OneBot11GroupRequest"]["properties"]["sub_type"] == {
        "type": "string",
        "description": "请求子类型",
    }


def test_normalize_ob11_event_schema_augments_napcat_notice_events():
    module = _load_module(
        "normalize_ob11_event_schema",
        "scripts/napcat/normalize_ob11_event_schema.py",
    )
    schema = {
        "$defs": {
            "OB11AllEvent": {
                "anyOf": [
                    {"$ref": "#/definitions/OB11PrivateMessage"},
                ]
            }
        },
    }

    fixed_count = module._augment_napcat_notice_event_schema(schema)

    assert fixed_count == 16
    refs = {
        item["$ref"]
        for item in schema["$defs"]["OB11AllEvent"]["anyOf"]
        if isinstance(item, dict) and "$ref" in item
    }
    assert "#/definitions/OneBot11BotOffline" in refs
    assert "#/definitions/OneBot11GroupGrayTip" in refs
    assert "#/definitions/OneBot11GroupName" in refs
    assert "#/definitions/OneBot11GroupTitle" in refs
    assert "#/definitions/OneBot11InputStatus" in refs
    assert "#/definitions/OneBot11ProfileLike" in refs
    assert "#/definitions/OneBot11OnlineFileReceive" in refs
    assert "#/definitions/OneBot11OnlineFileSend" in refs
    assert (
        schema["$defs"]["OneBot11OnlineFileSend"]["properties"]["notice_type"]["const"]
        == "online_file_send"
    )


def test_generated_napcat_modules_import() -> None:
    events_module = importlib.import_module(
        "astrbot.core.platform.sources.napcat.generated.ob11_events"
    )

    assert hasattr(events_module, "OB11AllEvent")
    assert "sender_id" in events_module.OneBot11Poke.model_fields
    assert "raw_info" in events_module.OneBot11Poke.model_fields
    assert "is_add" in events_module.OneBot11GroupMessageReaction.model_fields
    assert events_module.OneBot11GroupRequest.model_fields["sub_type"].annotation is str
