from datetime import datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy import inspect as sa_inspect


def convert_datetime_fields(
    row: dict[str, Any],
    model_class: type[Any],
) -> dict[str, Any]:
    """Convert ISO datetime strings to datetime objects for ORM models.

    Args:
        row: Raw row data from the backup payload.
        model_class: SQLAlchemy model class used for import.

    Returns:
        A shallow-copied row with datetime fields converted when possible.
    """

    converted = row.copy()

    try:
        mapper = sa_inspect(model_class)
    except Exception:
        return converted

    for column in mapper.columns:
        value = converted.get(column.name)
        if value is None or not isinstance(value, str):
            continue
        if isinstance(column.type, DateTime):
            converted[column.name] = datetime.fromisoformat(value)

    return converted
