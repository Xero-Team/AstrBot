import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_batch_update_sort_order_reorders_prompts_and_folders(
    temp_db: SQLiteDatabase,
):
    root_b = await temp_db.insert_prompt_folder(name="B", sort_order=20)
    root_a = await temp_db.insert_prompt_folder(name="A", sort_order=10)
    await temp_db.insert_prompt(
        prompt_id="prompt-b",
        system_prompt="prompt",
        folder_id=None,
        sort_order=20,
    )
    await temp_db.insert_prompt(
        prompt_id="prompt-a",
        system_prompt="prompt",
        folder_id=None,
        sort_order=10,
    )

    await temp_db.batch_update_sort_order(
        [
            {"id": root_b.folder_id, "type": "folder", "sort_order": 0},
            {"id": "prompt-b", "type": "prompt", "sort_order": 0},
            {"id": None, "type": "prompt", "sort_order": 99},
            {"id": root_a.folder_id, "type": "unknown", "sort_order": 0},
        ]
    )

    folders = await temp_db.get_prompt_folders()
    prompts = await temp_db.get_prompts_by_folder(None)

    assert [folder.name for folder in folders] == ["B", "A"]
    assert [prompt.prompt_id for prompt in prompts] == ["prompt-b", "prompt-a"]


@pytest.mark.asyncio
async def test_update_prompt_folder_can_clear_parent_and_description(
    temp_db: SQLiteDatabase,
):
    parent = await temp_db.insert_prompt_folder(name="Parent")
    child = await temp_db.insert_prompt_folder(
        name="Child",
        parent_id=parent.folder_id,
        description="desc",
        sort_order=5,
    )

    updated = await temp_db.update_prompt_folder(
        child.folder_id,
        parent_id=None,
        description=None,
        sort_order=1,
    )

    assert updated is not None
    assert updated.parent_id is None
    assert updated.description is None
    assert updated.sort_order == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True], ids=["root-folder", "nested-folder"])
async def test_delete_prompt_folder_preserves_children_and_prompts(
    temp_db: SQLiteDatabase,
    nested: bool,
) -> None:
    unrelated = await temp_db.insert_prompt_folder("Unrelated")
    parent_id = unrelated.folder_id if nested else None
    target = await temp_db.insert_prompt_folder("Target", parent_id=parent_id)
    child = await temp_db.insert_prompt_folder("Child", parent_id=target.folder_id)
    sibling = await temp_db.insert_prompt_folder("Sibling", parent_id=target.folder_id)
    grandchild = await temp_db.insert_prompt_folder(
        "Grandchild",
        parent_id=child.folder_id,
    )
    for name, folder in (
        ("direct", target),
        ("child", child),
        ("grandchild", grandchild),
        ("unrelated", unrelated),
    ):
        await temp_db.insert_prompt(name, "Test prompt", folder_id=folder.folder_id)

    await temp_db.delete_prompt_folder(target.folder_id)

    assert await temp_db.get_prompt_folder_by_id(target.folder_id) is None
    assert {folder.folder_id for folder in await temp_db.get_prompt_folders()} == {
        unrelated.folder_id,
        child.folder_id,
        sibling.folder_id,
    }
    assert {
        folder.folder_id for folder in await temp_db.get_prompt_folders(child.folder_id)
    } == {grandchild.folder_id}
    assert {folder.folder_id for folder in await temp_db.get_all_prompt_folders()} == {
        unrelated.folder_id,
        child.folder_id,
        sibling.folder_id,
        grandchild.folder_id,
    }
    assert {
        prompt.prompt_id: prompt.folder_id for prompt in await temp_db.get_prompts()
    } == {
        "direct": None,
        "child": child.folder_id,
        "grandchild": grandchild.folder_id,
        "unrelated": unrelated.folder_id,
    }
