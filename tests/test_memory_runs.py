from __future__ import annotations

import pytest

from ecosemantic.ports.run import RunPort
from tests.conformance.runs import RunConformance
from tests.memory_runs import MemoryRuns


class TestMemoryRuns(RunConformance):
    @pytest.fixture
    def runs(self) -> MemoryRuns:
        return MemoryRuns()

    def test_satisfies_the_port(self, runs: MemoryRuns) -> None:
        assert isinstance(runs, RunPort)
