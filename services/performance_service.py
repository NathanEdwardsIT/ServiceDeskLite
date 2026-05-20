from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Ticket, TicketSla, User
from app.models.enums import SlaStatus, TicketStatus, UserRole


class PerformanceService:
    def __init__(self, db: Session):
        self.db = db

    def technician_dashboard(self, days: int = 30) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        technicians = (
            self.db.query(User)
            .filter(User.role.in_([UserRole.TECHNICIAN.value, UserRole.TEAM_LEAD.value]))
            .all()
        )

        results = []
        for tech in technicians:
            assigned = (
                self.db.query(Ticket)
                .filter(
                    Ticket.assigned_technician_id == tech.id,
                    Ticket.created_at >= since,
                )
                .all()
            )
            resolved = [t for t in assigned if t.status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value)]
            breached = 0
            met = 0
            for t in resolved:
                if t.sla:
                    if t.sla.status == SlaStatus.BREACHED.value or t.sla.breached_at:
                        breached += 1
                    elif t.sla.status == SlaStatus.MET.value:
                        met += 1

            avg_resolution_hours = None
            durations = []
            for t in resolved:
                if t.resolved_at and t.created_at:
                    durations.append((t.resolved_at - t.created_at).total_seconds() / 3600)
            if durations:
                avg_resolution_hours = round(sum(durations) / len(durations), 2)

            results.append(
                {
                    "technician": tech,
                    "assigned_count": len(assigned),
                    "resolved_count": len(resolved),
                    "open_count": len(assigned) - len(resolved),
                    "sla_met": met,
                    "sla_breached": breached,
                    "sla_compliance_pct": round((met / len(resolved)) * 100, 1) if resolved else 100.0,
                    "avg_resolution_hours": avg_resolution_hours,
                }
            )

        results.sort(key=lambda x: x["resolved_count"], reverse=True)
        return results

    def queue_stats(self) -> dict:
        by_status = (
            self.db.query(Ticket.status, func.count(Ticket.id))
            .group_by(Ticket.status)
            .all()
        )
        at_risk = (
            self.db.query(TicketSla)
            .filter(TicketSla.status.in_([SlaStatus.AT_RISK.value, SlaStatus.BREACHED.value]))
            .count()
        )
        return {
            "by_status": dict(by_status),
            "sla_at_risk": at_risk,
            "total_open": sum(
                c for s, c in by_status if s not in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value, TicketStatus.CANCELLED.value)
            ),
        }
