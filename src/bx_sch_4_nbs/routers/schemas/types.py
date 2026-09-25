from typing import Annotated

from pydantic import AfterValidator

from bx_sch_4_nbs.helpers.common import parse_instagram
from bx_sch_4_nbs.helpers.security import normalize_phone

InstagramHandle = Annotated[str, AfterValidator(parse_instagram)]
PhoneNumber = Annotated[str, AfterValidator(normalize_phone)]
