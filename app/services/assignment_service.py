from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Ticket, User
from app.models.enums import TicketStatus, UserRole


class AssignmentService:
    """Round-robin + workload-balanced technician assignment."""

    def __init__(self, db: Session):
        self.db = db

    def get_available_technicians(self) -> list[User]:
        return (
            self.db.query(User)
            .filter(
                User.is_active.is_(True),
                User.role.in_([UserRole.TECHNICIAN.value, UserRole.TEAM_LEAD.value]),
            )
            .all()
        )

    def get_open_ticket_counts(self) -> dict[int, int]:
        rows = (
            self.db.query(Ticket.assigned_technician_id, func.count(Ticket.id))
            .filter(
                Ticket.assigned_technician_id.isnot(None),
                Ticket.status.in_(
                    [
                        TicketStatus.NEW.value,
                        TicketStatus.OPEN.value,
                        TicketStatus.IN_PROGRESS.value,
                        TicketStatus.PENDING.value,
                    ]
                ),
            )
            .group_by(Ticket.assigned_technician_id)
            .all()
        )
        return {tech_id: count for tech_id, count in rows}

    def assign_best_technician(self, ticket: Ticket, category: str | None = None) -> User | None:
        technicians = self.get_available_technicians()
        if not technicians:
            return None

        workloads = self.get_open_ticket_counts()

        # Prefer technicians with matching department for hardware/network categories
        if category in ("hardware", "network"):
            dept_match = [t for t in technicians if t.department == "Infrastructure"]
            if dept_match:
                technicians = dept_match

        # Lowest open ticket count wins; tie-break by user id for determinism
        chosen = min(
            technicians,
            key=lambda t: (workloads.get(t.id, 0), t.id),
        )
        ticket.assigned_technician_id = chosen.id
        if ticket.status == TicketStatus.NEW.value:
            ticket.status = TicketStatus.OPEN.value
        self.db.flush()
        return chosen

    def manual_assign(self, ticket: Ticket, technician_id: int) -> User | None:
        tech = (
            self.db.query(User)
            .filter(
                User.id == technician_id,
                User.role.in_([UserRole.TECHNICIAN.value, UserRole.TEAM_LEAD.value]),
            )
            .first()
        )
        if not tech:
            return None
        ticket.assigned_technician_id = tech.id
        if ticket.status == TicketStatus.NEW.value:
            ticket.status = TicketStatus.OPEN.value
        self.db.flush()
        return tech
