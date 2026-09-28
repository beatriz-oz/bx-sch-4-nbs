from datetime import date, datetime

from pydantic import BaseModel


class AvailableDay(BaseModel):
    day: date
    slots: list[datetime]
