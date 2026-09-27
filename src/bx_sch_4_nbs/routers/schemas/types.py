from typing import Annotated

from pydantic import AfterValidator, Field

from bx_sch_4_nbs.helpers.common import parse_instagram
from bx_sch_4_nbs.helpers.security import normalize_phone

Password = Annotated[str, Field(min_length=8, max_length=128, json_schema_extra={"format": "password"})]

InstagramHandle = Annotated[str, AfterValidator(parse_instagram)]
PhoneNumber = Annotated[str, AfterValidator(normalize_phone)]
