"""Typed questions and answers for classifier providers (not chat models)."""

import math
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

type ClassifierInput = str | dict[str, Any] | list[Any]
type Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _TypedValue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class NoulQuestion(_TypedValue):
    type: Literal["noul"] = "noul"
    instructions: ClassifierInput
    criteria: dict[Literal["true", "false"], ClassifierInput] | None = None


class ChoiceQuestion(_TypedValue):
    type: Literal["choice"] = "choice"
    instructions: ClassifierInput
    criteria: Annotated[
        dict[str, ClassifierInput | None], Field(min_length=2, max_length=255)
    ]


class ScoreQuestion(_TypedValue):
    type: Literal["score"] = "score"
    instructions: ClassifierInput
    criteria: Annotated[list[ClassifierInput], Field(min_length=2, max_length=10)]


type ClassifierQuestion = NoulQuestion | ChoiceQuestion | ScoreQuestion


class NoulAnswer(_TypedValue):
    type: Literal["noul"]
    noul: Probability


class _DistributionAnswer(_TypedValue):
    probabilities: dict[str, Probability]
    confidence: Probability

    @model_validator(mode="after")
    def valid_distribution(self):
        if not self.probabilities or not math.isclose(
            sum(self.probabilities.values()), 1, abs_tol=0.001
        ):
            raise ValueError("Invalid classifier probability distribution")
        return self


class ChoiceAnswer(_DistributionAnswer):
    type: Literal["choice"]
    choice: str

    @model_validator(mode="after")
    def valid_choice(self):
        if self.probabilities.get(self.choice, -1) != max(self.probabilities.values()):
            raise ValueError("Classifier choice must have the highest probability")
        return self


class ScoreAnswer(_DistributionAnswer):
    type: Literal["score"]
    score: Annotated[float, Field(allow_inf_nan=False)]
    legend: dict[str, str]

    @model_validator(mode="after")
    def valid_score(self):
        levels = {str(i) for i in range(len(self.legend))}
        if (
            not 2 <= len(levels) <= 10
            or set(self.probabilities) != levels
            or set(self.legend) != levels
        ):
            raise ValueError("Invalid classifier score levels")
        weighted = sum(int(k) * v for k, v in self.probabilities.items())
        if not math.isclose(self.score, weighted, abs_tol=0.01):
            raise ValueError("Invalid classifier weighted score")
        return self


type ClassifierAnswer = Annotated[
    NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")
]


class ClassifierUsage(_TypedValue):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]


class ClassifierResult(_TypedValue):
    model: Annotated[str, Field(min_length=1)]
    answers: dict[str, ClassifierAnswer]
    usage: ClassifierUsage

    def validate_questions(self, questions: dict[str, ClassifierQuestion]) -> None:
        """Reject missing answers, mismatched types and invented options."""
        if set(self.answers) != set(questions):
            raise ValueError("Classifier answer ids do not match questions")
        for name, question in questions.items():
            answer = self.answers[name]
            if answer.type != question.type:
                raise ValueError("Classifier answer type does not match question")
            if isinstance(question, ChoiceQuestion) and isinstance(
                answer, ChoiceAnswer
            ):
                if set(answer.probabilities) != set(question.criteria):
                    raise ValueError("Classifier choices do not match criteria")
            if isinstance(question, ScoreQuestion) and isinstance(answer, ScoreAnswer):
                if len(answer.legend) != len(question.criteria):
                    raise ValueError("Classifier score levels do not match criteria")


@runtime_checkable
class ClassifierModel(Protocol):
    """Provider-neutral typed-decision contract consumed by Agent routing."""

    def get_model(self) -> str: ...

    async def evaluate(
        self, state: ClassifierInput, questions: dict[str, ClassifierQuestion]
    ) -> ClassifierResult: ...
