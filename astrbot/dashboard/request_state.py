from typing import Any


class DashboardRequestState:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def get(self, key: str, default: Any = None):
        return self._values.get(key, default)

    def __getattr__(self, key: str):
        try:
            return self._values[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_values":
            super().__setattr__(key, value)
            return
        self._values[key] = value
