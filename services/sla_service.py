from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import Ticket, TicketSla
from app.models.enums import SlaStatus, TicketPriority, TicketStatus


class SlaService:
    PRIORITY_MINUTES = {
        TicketPriority.CRITICAL.value: settings.sla_critical_minutes,
        TicketPriority.HIGH.value: settings.sla_high_minutes,
        TicketPriority.MEDIUM.value: settings.sla_medium_minutes,
        TicketPriority.LOW.value: settings.sla_low_minutes,
    }

    PAUSE_STATUSES = {TicketStatus.PENDING.value}

    def __init__(self, db: Session):
        self.db = db

    def create_sla(self, ticket: Ticket) -> TicketSla:
        target = self.PRIORITY_MINUTES.get(ticket.priority, settings.sla_medium_minutes)
        now = datetime.utcnow()
        sla = TicketSla(
            ticket_id=ticket.id,
            target_minutes=target,
            started_at=now,
            due_at=now + timedelta(minutes=target),
            status=SlaStatus.ON_TRACK.value,
            percent_remaining=100.0,
        )
        self.db.add(sla)
        self.db.flush()
        return sla

    def refresh(self, ticket: Ticket) -> TicketSla | None:
        sla = ticket.sla
        if not sla:
            return None

        if ticket.status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
            if not sla.met_at:
                sla.met_at = datetime.utcnow()
                sla.status = (
                    SlaStatus.BREACHED.value
                    if sla.breached_at
                    else SlaStatus.MET.value
                )
            sla.percent_remaining = 0.0
            return sla

        now = datetime.utcnow()

        if ticket.status in self.PAUSE_STATUSES:
            if not sla.paused_at:
                sla.paused_at = now
                sla.status = SlaStatus.PAUSED.value
            return sla

        if sla.paused_at:
            paused_delta = int((now - sla.paused_at).total_seconds() / 60)
            sla.paused_minutes += paused_delta
            sla.paused_at = None
            sla.due_at = sla.due_at + timedelta(minutes=paused_delta)

        elapsed = (now - sla.started_at).total_seconds() / 60 - sla.paused_minutes
        remaining = sla.target_minutes - elapsed
        sla.percent_remaining = max(0.0, min(100.0, (remaining / sla.target_minutes) * 100))

        if now > sla.due_at and not sla.breached_at:
            sla.breached_at = now
            sla.status = SlaStatus.BREACHED.value
        elif sla.percent_remaining <= 25:
            sla.status = SlaStatus.AT_RISK.value
        else:
            sla.status = SlaStatus.ON_TRACK.value

        return sla

    def format_timer_display(self, sla: TicketSla) -> dict:
        now = datetime.utcnow()
        if sla.met_at:
            return {
                "label": "SLA Met" if sla.status == SlaStatus.MET.value else "SLA Breached",
                "remaining_minutes": 0,
                "due_at": sla.due_at.isoformat(),
                "status": sla.status,
                "percent_remaining": sla.percent_remaining,
            }

        remaining_seconds = max(0, (sla.due_at - now).total_seconds())
        remaining_minutes = int(remaining_seconds / 60)
        hours, mins = divmod(remaining_minutes, 60)

        return {
            "label": f"{hours}h {mins}m remaining" if remaining_minutes else "Overdue",
            "remaining_minutes": remaining_minutes,
            "due_at": sla.due_at.isoformat(),
            "status": sla.status,
            "percent_remaining": round(sla.percent_remaining, 1),
        }
