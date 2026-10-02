from typing import Literal, TypeVar

from pydantic import BaseModel

from bx_sch_4_nbs.routers.schemas import admin, appointments, auth, prices, schedule

T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    page_number: int
    page_content_size: int
    total: int
    size: int


class BaseResponse[T](BaseModel):
    status: Literal["OK", "KO"]
    detail: T


class BaseResponseWithWarning[T](BaseResponse[T]):
    warning: str | None = None


MessageResponse = BaseResponse[str]
PreApprovedInstagramResponse = BaseResponse[admin.PreApprovedInstagramResult]
PreApprovedInstagramListResponse = BaseResponse[list[admin.PreApprovedInstagramResult]]
CodeSentResponse = BaseResponse[auth.CodeSent]
TokenResponse = BaseResponse[auth.TokenResult]
UserResponse = BaseResponse[auth.UserResult]
AvailabilityResponse = BaseResponse[list[appointments.AvailableDay]]
PolicyResponse = BaseResponse[admin.PolicyResult]
PriceListResponse = BaseResponse[prices.PriceList]
ServicePriceResponse = BaseResponse[prices.ServicePriceResult]
NailArtPriceResponse = BaseResponse[prices.NailArtPriceResult]
AddonPriceResponse = BaseResponse[prices.AddonPriceResult]
ScheduleExceptionResponse = BaseResponseWithWarning[schedule.ScheduleExceptionResult]
ScheduleExceptionListResponse = BaseResponse[list[schedule.ScheduleExceptionResult]]
MonthPublishedResponse = BaseResponse[schedule.MonthPublished]
PublishedMonthListResponse = BaseResponse[list[schedule.PublishedMonthResult]]
AvailabilityPreviewResponse = BaseResponse[appointments.AvailabilityPreview]
EstimateResponse = BaseResponse[appointments.EstimateResult]
NewAppointmentResponse = BaseResponse[appointments.BookingResult]
CancellationResponse = BaseResponse[appointments.CancellationResult]
AppointmentResponse = BaseResponse[appointments.AppointmentResult]
AdminAppointmentListResponse = BaseResponse[list[admin.AdminAppointmentResult]]
AdminAppointmentResponse = BaseResponse[admin.AdminAppointmentResult]
