"""
The appointments of a period as an Excel file (.xlsx), to open in Google Sheets or Excel.

Real types on purpose: dates are dates, prices are numbers. A CSV would be text, and a
Portuguese spreadsheet reads "12.50" as text (it expects "12,50"), so the sums would break.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Literal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries.reports import keeps_deposit
from bx_sch_4_nbs.database.queries.schedule import duration_minutes
from bx_sch_4_nbs.database.types import AppointmentStatus, CancellationReason, Service
from bx_sch_4_nbs.helpers.common import to_studio_time

Language = Literal["pt", "en"]

EURO = '#,##0.00 "€"'
HEADER_FILL = PatternFill("solid", fgColor="751452")

TEXTS: dict[Language, dict[str, str]] = {
    "pt": {
        "sheet": "Marcações",
        "date": "Data",
        "time": "Hora",
        "client": "Cliente",
        "instagram": "Instagram",
        "service": "Serviço",
        "size": "Tamanho",
        "art": "Nail art",
        "broken": "Unhas partidas",
        "status": "Estado",
        "reason": "Motivo do cancelamento",
        "estimated": "Preço estimado",
        "final": "Preço final",
        "deposit_paid": "Sinal pago",
        "deposit_refunded": "Sinal devolvido",
        "received": "Recebido",
        "duration": "Duração (min)",
        "notes": "Notas",
        "completion_notes": "Notas da conclusão",
        "yes": "Sim",
        "no": "Não",
        "total": "Total",
    },
    "en": {
        "sheet": "Appointments",
        "date": "Date",
        "time": "Time",
        "client": "Client",
        "instagram": "Instagram",
        "service": "Service",
        "size": "Size",
        "art": "Nail art",
        "broken": "Broken nails",
        "status": "Status",
        "reason": "Cancellation reason",
        "estimated": "Estimated price",
        "final": "Final price",
        "deposit_paid": "Deposit paid",
        "deposit_refunded": "Deposit refunded",
        "received": "Received",
        "duration": "Duration (min)",
        "notes": "Notes",
        "completion_notes": "Completion notes",
        "yes": "Yes",
        "no": "No",
        "total": "Total",
    },
}

SERVICES: dict[Language, dict[Service, str]] = {
    "pt": {
        Service.APPLICATION: "Aplicação",
        Service.MAINTENANCE: "Manutenção",
        Service.REMOVAL: "Remoção",
        Service.OTHER: "Outro",
    },
    "en": {
        Service.APPLICATION: "Application",
        Service.MAINTENANCE: "Maintenance",
        Service.REMOVAL: "Removal",
        Service.OTHER: "Other",
    },
}

STATUSES: dict[Language, dict[AppointmentStatus, str]] = {
    "pt": {
        AppointmentStatus.SCHEDULED: "Marcada",
        AppointmentStatus.CONFIRMED: "Confirmada",
        AppointmentStatus.COMPLETED: "Concluída",
        AppointmentStatus.CANCELLED: "Cancelada",
        AppointmentStatus.NO_SHOW: "Faltou",
    },
    "en": {
        AppointmentStatus.SCHEDULED: "Scheduled",
        AppointmentStatus.CONFIRMED: "Confirmed",
        AppointmentStatus.COMPLETED: "Completed",
        AppointmentStatus.CANCELLED: "Cancelled",
        AppointmentStatus.NO_SHOW: "No-show",
    },
}

REASONS: dict[Language, dict[CancellationReason, str]] = {
    "pt": {
        CancellationReason.CLIENT_EARLY: "Pela cliente, mais de 48h antes",
        CancellationReason.CLIENT_LATE: "Pela cliente, menos de 48h antes",
        CancellationReason.NOT_CONFIRMED: "Presença não confirmada",
        CancellationReason.BY_STUDIO: "Pelo estúdio",
    },
    "en": {reason: reason.value for reason in CancellationReason},
}


def received(appointment: Appointment, deposit_amount: Decimal) -> Decimal:
    """What the studio actually got: the price of a completed appointment, or a kept deposit."""
    if appointment.status == AppointmentStatus.COMPLETED:
        return appointment.final_price if appointment.final_price is not None else appointment.estimated_price
    if keeps_deposit(appointment):
        return deposit_amount
    return Decimal(0)


def appointments_workbook(rows: list[tuple[Appointment, User]], language: Language, deposit_amount: Decimal) -> bytes:
    texts = TEXTS[language]
    yes_no = {True: texts["yes"], False: texts["no"]}

    book = Workbook()
    sheet = book.active
    if sheet is None:
        raise RuntimeError("A new workbook always has a sheet.")
    sheet.title = texts["sheet"]

    columns = [
        ("date", 12, "DD/MM/YYYY"),
        ("time", 8, "HH:MM"),
        ("client", 24, None),
        ("instagram", 20, None),
        ("service", 14, None),
        ("size", 9, None),
        ("art", 10, None),
        ("broken", 9, None),
        ("status", 12, None),
        ("reason", 30, None),
        ("estimated", 13, EURO),
        ("final", 13, EURO),
        ("deposit_paid", 11, None),
        ("deposit_refunded", 13, None),
        ("received", 13, EURO),
        ("duration", 11, None),
        ("notes", 40, None),
        ("completion_notes", 40, None),
    ]
    sheet.append([texts[key] for key, _, _ in columns])
    for index, (_, width, _) in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
        cell = sheet.cell(row=1, column=index)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL

    for appointment, user in rows:
        when = to_studio_time(appointment.scheduled_at).replace(tzinfo=None)
        sheet.append(
            [
                when.date(),
                when.time(),
                f"{user.name} {user.last_name}",
                f"@{user.instagram}" if user.instagram else "",
                SERVICES[language][appointment.service],
                appointment.nail_size.value if appointment.nail_size else "",
                appointment.nail_art_level.value if appointment.nail_art_level else "",
                appointment.broken_nails or None,
                STATUSES[language][appointment.status],
                REASONS[language][appointment.cancellation_reason] if appointment.cancellation_reason else "",
                appointment.estimated_price,
                appointment.final_price,
                yes_no[appointment.deposit_paid_at is not None],
                yes_no[appointment.deposit_refunded_at is not None] if appointment.deposit_paid_at else "",
                received(appointment, deposit_amount),
                duration_minutes(appointment) if appointment.status == AppointmentStatus.COMPLETED else None,
                appointment.notes or "",
                appointment.completion_notes or "",
            ]
        )

    last = sheet.max_row
    for index, (_, _, number_format) in enumerate(columns, start=1):
        if number_format:
            for row in range(2, last + 1):
                sheet.cell(row=row, column=index).number_format = number_format

    # A formula, not a fixed number: it stays right if she edits or filters rows in the sheet.
    received_column = get_column_letter([key for key, _, _ in columns].index("received") + 1)
    total_row = last + 2
    sheet.cell(row=total_row, column=1, value=texts["total"]).font = Font(bold=True)
    total = sheet[f"{received_column}{total_row}"]
    total.value = f"=SUM({received_column}2:{received_column}{max(last, 2)})"
    total.number_format = EURO
    total.font = Font(bold=True)

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(last, 1)}"

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def export_filename(first_day: date, last_day: date, language: Language) -> str:
    name = "marcacoes" if language == "pt" else "appointments"
    return f"{name}_{first_day.isoformat()}_{last_day.isoformat()}.xlsx"
