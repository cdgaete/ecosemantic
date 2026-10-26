from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.activity import ACTIVITY_DIR, FilesystemActivity
from ecosemantic.errors import Unavailable
from ecosemantic.ports.activity import ActivityPort
from tests.conformance.activity import ActivityConformance, draft


class TestFilesystemActivity(ActivityConformance):
    @pytest.fixture
    def activity(self, tmp_path: Path) -> FilesystemActivity:
        return FilesystemActivity(tmp_path)

    def test_satisfies_the_port(self, activity: FilesystemActivity) -> None:
        assert isinstance(activity, ActivityPort)

    async def test_an_agent_is_one_file_of_one_line_per_call(
        self, activity: FilesystemActivity, tmp_path: Path
    ) -> None:
        first = await activity.record(draft("electricity", "a", 1))
        await activity.record(draft("electricity", "b", 2))
        await activity.record(draft("packaging", "c", 3))
        lines = (
            (tmp_path / ACTIVITY_DIR / "electricity.jsonl").read_text(encoding="utf-8").splitlines()
        )
        assert len(lines) == 2 and json.loads(lines[0])["id"] == str(first.id)
        assert (tmp_path / ACTIVITY_DIR / "packaging.jsonl").is_file()

    async def test_a_second_instance_over_the_directory_reads_what_the_first_wrote(
        self, activity: FilesystemActivity, tmp_path: Path
    ) -> None:
        recorded = await activity.record(draft("electricity", "a", 1))
        assert await FilesystemActivity(tmp_path).get_call(recorded.id) == recorded

    async def test_a_directory_with_no_activity_lists_nothing(
        self, activity: FilesystemActivity
    ) -> None:
        assert await activity.list_calls() == [] and await activity.list_agents() == []
        assert await activity.list_calls(agent="electricity") == []

    async def test_a_line_this_version_cannot_read_names_its_file_and_line(
        self, activity: FilesystemActivity, tmp_path: Path
    ) -> None:
        await activity.record(draft("electricity", "a", 1))
        with (tmp_path / ACTIVITY_DIR / "electricity.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"agent": "electricity"}\n')
        with pytest.raises(Unavailable, match="electricity.jsonl line 2"):
            await activity.list_calls()
