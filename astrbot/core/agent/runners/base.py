import abc
import typing as T
from enum import Enum, auto

from astrbot import logger

from ..hooks import BaseAgentRunHooks
from ..llm_types import LLMResponse
from ..response import AgentResponse
from ..run_context import ContextWrapper


class AgentState(Enum):
    """Defines the state of the agent."""

    IDLE = auto()  # Initial state
    RUNNING = auto()  # Currently processing
    DONE = auto()  # Completed
    ERROR = auto()  # Error state


class BaseAgentRunner[TContext]:
    @abc.abstractmethod
    async def reset(
        self,
        *args: T.Any,
        run_context: ContextWrapper[TContext] | None = None,
        agent_hooks: BaseAgentRunHooks[TContext] | None = None,
        **kwargs: T.Any,
    ) -> None:
        """Reset the agent to its initial state.
        This method should be called before starting a new run.
        """
        ...

    @abc.abstractmethod
    def step(self) -> T.AsyncGenerator[AgentResponse]:
        """Process a single step of the agent."""
        ...

    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse]:
        """Process steps until the agent is done."""
        if max_step <= 0:
            raise ValueError("max_step must be greater than 0")

        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for response in self.step():
                yield response

        if not self.done():
            raise RuntimeError(
                f"{type(self).__name__} reached max_step ({max_step}) without completion."
            )

    @abc.abstractmethod
    def done(self) -> bool:
        """Check if the agent has completed its task.
        Returns True if the agent is done, False otherwise.
        """
        ...

    @abc.abstractmethod
    def get_final_llm_resp(self) -> LLMResponse | None:
        """Get the final observation from the agent.
        This method should be called after the agent is done.
        """
        ...

    def _transition_state(self, new_state: AgentState) -> None:
        """Transition the agent state."""
        if self._state != new_state:
            logger.debug(f"Agent state transition: {self._state} -> {new_state}")
            self._state = new_state
