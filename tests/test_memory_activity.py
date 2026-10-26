from __future__ import annotations

import pytest

from ecosemantic.ports.activity import ActivityPort
from tests.conformance.activity import ActivityConformance
from tests.memory_activity import MemoryActivity


class TestMemoryActivity(ActivityConformance):
    @pytest.fixture
    def activity(self) -> MemoryActivity:
        return MemoryActivity()

    def test_satisfies_the_port(self, activity: MemoryActivity) -> None:
        assert isinstance(activity, ActivityPort)
