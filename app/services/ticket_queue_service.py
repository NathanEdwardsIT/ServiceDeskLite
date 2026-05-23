"""Ticket queue analytics and filtering helpers."""

from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.entities import Ticket, User
from app.models.enums import TicketStatus
from app.services.sla_service import SlaService


class TicketQueueService:
    def __init__(self, db: Session):
        self.db = db
        self.sla = SlaService(db)

    def queue_stats(self, tickets: list[Ticket] | None = None) -> dict:
        if tickets is None:
            tickets = self.db.query(Ticket).all()
        open_statuses = {
            TicketStatus.NEW.value,
            TicketStatus.OPEN.value,
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.PENDING.value,
        }
        open_tickets = [t for t in tickets if t.status in open_statuses]
        breached = 0
        for t in open_tickets:
            if t.sla:
                self.sla.refresh(t)
                if t.sla.status == "breached":
                    breached += 1
        by_status: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        for t in open_tickets:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        escalated = sum(1 for t in open_tickets if (t.escalation_level or 0) > 0)
        unassigned = sum(1 for t in open_tickets if not t.assigned_technician_id)
        return {
            "total_open": len(open_tickets),
            "breached_sla": breached,
            "escalated": escalated,
            "unassigned": unassigned,
            "by_status": by_status,
            "by_priority": by_priority,
        }

    def search_tickets(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        ticket_type: str | None = None,
        category: str | None = None,
        assigned_to: int | None = None,
        requester_id: int | None = None,
        escalated_only: bool = False,
        sla_status: str | None = None,
        sort: str = "newest",
        page: int = 1,
        per_page: int = 25,
        user_scope: tuple[int, bool] | None = None,
    ) -> dict:
        """Search with pagination. user_scope = (user_id, view_all)."""
        q = self.db.query(Ticket).options(
            joinedload(Ticket.sla),
            joinedload(Ticket.assigned_technician),
            joinedload(Ticket.requester),
        )

        if user_scope and not user_scope[1]:
            uid = user_scope[0]
            q = q.filter(
                or_(Ticket.requester_id == uid, Ticket.assigned_technician_id == uid)
            )

        if query:
            pattern = f"%{query}%"
            q = q.filter(
                or_(
                    Ticket.title.ilike(pattern),
                    Ticket.description.ilike(pattern),
                    Ticket.ticket_number.ilike(pattern),
                    Ticket.tags.ilike(pattern),
                )
            )
        if status:
            q = q.filter(Ticket.status == status)
        if priority:
            q = q.filter(Ticket.priority == priority)
        if ticket_type:
            q = q.filter(Ticket.ticket_type == ticket_type)
        if category:
            q = q.filter(Ticket.category == category)
        if assigned_to:
            q = q.filter(Ticket.assigned_technician_id == assigned_to)
        if requester_id:
            q = q.filter(Ticket.requester_id == requester_id)
        if escalated_only:
            q = q.filter(Ticket.escalation_level > 0)

        if sort == "oldest":
            q = q.order_by(Ticket.created_at.asc())
        else:
            q = q.order_by(Ticket.created_at.desc())

        total = q.count()
        page = max(1, page)
        per_page = min(max(1, per_page), 100)
        items = q.offset((page - 1) * per_page).limit(per_page).all()

        if sort == "priority":
            _prio = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            items.sort(key=lambda t: (_prio.get(t.priority, 9), t.created_at), reverse=False)

        if sla_status:
            filtered = []
            for t in items:
                if t.sla:
                    self.sla.refresh(t)
                    if t.sla.status == sla_status:
                        filtered.append(t)
            items = filtered

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }

    def kanban_board(self, user_scope: tuple[int, bool] | None = None) -> dict:
        from app.services.workflow_service import WorkflowService

        wf = WorkflowService()
        columns = wf.kanban_columns()
        q = self.db.query(Ticket).options(
            joinedload(Ticket.sla),
            joinedload(Ticket.assigned_technician),
            joinedload(Ticket.requester),
        )
        if user_scope and not user_scope[1]:
            uid = user_scope[0]
            q = q.filter(
                or_(Ticket.requester_id == uid, Ticket.assigned_technician_id == uid)
            )
        open_statuses = {c["id"] for c in columns}
        tickets = q.filter(Ticket.status.in_(open_statuses)).order_by(Ticket.created_at.desc()).all()

        board: dict[str, list] = {c["id"]: [] for c in columns}
        for t in tickets:
            if t.status in board:
                sla_info = None
                if t.sla:
                    self.sla.refresh(t)
                    sla_info = self.sla.format_timer_display(t.sla)
                board[t.status].append(
                    {
                        "id": t.id,
                        "number": t.ticket_number,
                        "title": t.title,
                        "priority": t.priority,
                        "assigned": t.assigned_technician.display_name if t.assigned_technician else None,
                        "escalation_level": t.escalation_level or 0,
                        "sla": sla_info,
                        "created_at": t.created_at.isoformat(),
                    }
                )
        return {"columns": columns, "board": board}

    def technician_workload(self) -> list[dict]:
        open_statuses = (
            TicketStatus.NEW.value,
            TicketStatus.OPEN.value,
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.PENDING.value,
        )
        techs = (
            self.db.query(User)
            .filter(User.role.in_(("technician", "team_lead", "admin")), User.is_active.is_(True))
            .all()
        )
        result = []
        for tech in techs:
            count = (
                self.db.query(Ticket)
                .filter(
                    Ticket.assigned_technician_id == tech.id,
                    Ticket.status.in_(open_statuses),
                )
                .count()
            )
            result.append({"id": tech.id, "name": tech.display_name, "open_count": count})
        return sorted(result, key=lambda x: x["open_count"])
