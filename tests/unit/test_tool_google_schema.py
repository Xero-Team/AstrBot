from copy import deepcopy

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.function_tool_manager import FunctionToolManager

_OPTIONAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "category": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
        },
        "query": {
            "oneOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
        },
        "period": {
            "type": ["string", "null"],
            "default": None,
        },
        "union": {
            "anyOf": [{"type": "string"}, {"type": "integer"}],
        },
        "nullable_union": {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
                {"type": "null"},
            ],
        },
        "mixed_period": {
            "type": ["string", "integer", "null"],
            "default": None,
        },
        "filter": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "default": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
        },
        "tags": {
            "type": "array",
            "items": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
        },
    },
}


def _optional_string_tool() -> FunctionTool:
    return FunctionTool(
        name="browse",
        description="Browse.",
        parameters=deepcopy(_OPTIONAL_PARAMETERS),
    )


def test_google_schema_fills_missing_array_items_with_string_schema():
    tool = FunctionTool(
        name="search_sources",
        description="Search sources by UUID.",
        parameters={
            "type": "object",
            "properties": {
                "source_uuids": {
                    "type": "array",
                    "description": "Optional list of source UUIDs.",
                }
            },
            "required": ["source_uuids"],
        },
    )

    schema = ToolSet([tool]).google_schema()
    source_uuids = schema["function_declarations"][0]["parameters"]["properties"][
        "source_uuids"
    ]

    assert source_uuids["type"] == "array"
    assert source_uuids["items"] == {"type": "string"}


def test_openai_schema_sorts_tools_by_name_without_mutating_toolset_order():
    toolset = ToolSet(
        [
            FunctionTool(
                name="zebra",
                description="Zebra tool.",
                parameters={"type": "object", "properties": {}},
            ),
            FunctionTool(
                name="alpha",
                description="Alpha tool.",
                parameters={"type": "object", "properties": {}},
            ),
            FunctionTool(
                name="middle",
                description="Middle tool.",
                parameters={"type": "object", "properties": {}},
            ),
        ]
    )

    schema = toolset.openai_chat_completions_schema()

    assert [tool["function"]["name"] for tool in schema] == [
        "alpha",
        "middle",
        "zebra",
    ]
    assert [tool.name for tool in toolset.tools] == ["zebra", "alpha", "middle"]


def test_google_schema_flattens_optional_null_unions_without_mutating_parameters():
    tool = _optional_string_tool()
    original = deepcopy(tool.parameters)

    properties = ToolSet([tool]).google_schema()["function_declarations"][0][
        "parameters"
    ]["properties"]

    assert properties["category"] == {"type": "string", "nullable": True}
    assert properties["query"] == {"type": "string", "nullable": True}
    assert properties["period"] == {"type": "string", "nullable": True}
    assert properties["union"] == {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert "type" not in properties["union"]
    assert properties["nullable_union"] == {
        "anyOf": [
            {"type": "string"},
            {"type": "integer"},
            {"type": "null"},
        ]
    }
    assert "nullable" not in properties["nullable_union"]
    assert properties["filter"] == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }
    assert properties["tags"]["type"] == "array"
    assert properties["tags"]["items"] == {"type": "string", "nullable": True}
    assert tool.parameters == original


def test_openai_schema_keeps_json_schema_null_unions_by_default():
    tool = _optional_string_tool()

    properties = ToolSet([tool]).openai_chat_completions_schema()[0]["function"][
        "parameters"
    ]["properties"]

    assert properties["category"] == _OPTIONAL_PARAMETERS["properties"]["category"]
    assert properties["query"] == _OPTIONAL_PARAMETERS["properties"]["query"]
    assert properties["period"] == _OPTIONAL_PARAMETERS["properties"]["period"]
    assert properties["union"] == _OPTIONAL_PARAMETERS["properties"]["union"]


def test_openai_schema_flattens_null_unions_when_requested_without_mutating_parameters():
    tool = _optional_string_tool()
    original = deepcopy(tool.parameters)

    properties = ToolSet([tool]).openai_chat_completions_schema(
        flatten_null_unions=True
    )[0]["function"]["parameters"]["properties"]

    assert properties["category"]["type"] == "string"
    assert properties["category"]["nullable"] is True
    assert "anyOf" not in properties["category"]
    assert properties["query"]["type"] == "string"
    assert properties["query"]["nullable"] is True
    assert "oneOf" not in properties["query"]
    assert properties["period"] == {
        "type": "string",
        "default": None,
        "nullable": True,
    }
    assert properties["union"] == {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert (
        properties["nullable_union"]
        == _OPTIONAL_PARAMETERS["properties"]["nullable_union"]
    )
    assert "nullable" not in properties["nullable_union"]
    assert (
        properties["mixed_period"] == _OPTIONAL_PARAMETERS["properties"]["mixed_period"]
    )
    assert properties["filter"]["default"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    assert properties["tags"]["items"] == {"type": "string", "nullable": True}
    assert tool.parameters == original


def test_function_tool_manager_forwards_flatten_null_unions():
    tool = _optional_string_tool()
    manager = FunctionToolManager()
    manager.func_list.append(tool)

    properties = manager.openai_chat_completions_schema(flatten_null_unions=True)[0][
        "function"
    ]["parameters"]["properties"]

    assert properties["category"]["type"] == "string"
    assert properties["category"]["nullable"] is True
    assert "anyOf" not in properties["category"]
