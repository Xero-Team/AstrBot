import pytest

from astrbot.core.agent.response import AgentResponse
from astrbot.core.agent.runners.base import BaseAgentRunner


class ContractRunner(BaseAgentRunner[None]):
    def __init__(self, complete: bool) -> None:
        self.complete = complete
        self.steps = 0

    async def reset(self, **_kwargs) -> None:
        return None

    async def step(self):
        self.steps += 1
        if self.complete:
            self.complete = False
        yield AgentResponse(type="llm_result", data={"chain": None})

    def done(self) -> bool:
        return not self.complete

    def get_final_llm_resp(self):
        return None


@pytest.mark.asyncio
async def test_default_step_until_done_completes_and_validates_limit():
    runner = ContractRunner(complete=True)
    assert len([response async for response in runner.step_until_done(1)]) == 1
    assert runner.steps == 1

    with pytest.raises(ValueError, match="max_step must be greater than 0"):
        async for _ in runner.step_until_done(0):
            pass


@pytest.mark.asyncio
async def test_default_step_until_done_names_the_concrete_runner_on_limit():
    runner = ContractRunner(complete=False)
    # Keep the runner unfinished after each step.
    runner.done = lambda: False

    with pytest.raises(RuntimeError, match=r"ContractRunner reached max_step \(2\)"):
        async for _ in runner.step_until_done(2):
            pass
