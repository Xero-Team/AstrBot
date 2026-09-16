from dataclasses import dataclass


@dataclass
class Result:
    similarity: float
    data: dict
