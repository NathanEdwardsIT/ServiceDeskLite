from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.entities import Ticket, TicketStatusHistory
from app.models.enums import AuditAction, TicketStatus
from app.services.assignment_service import AssignmentService
from app.services.audit_service import AuditService
from app.services.auto_resolve_service import AutoResolveService
from app.services.documentation_service import DocumentationService
from app.services.duplicate_service import DuplicateDetectionService
from app.services.kb_service import KnowledgeBaseService
from app.services.sla_service import SlaService


class TicketService:
    def __init__(self, db: Session):
        self.db = db
        self.sla = SlaService(db)
        self.assignment = AssignmentService(db)
        self.duplicates = DuplicateDetectionService(db)
        self.kb = KnowledgeBaseService(db)
        self.docs = DocumentationService(db)
        self.auto_resolve = AutoResolveService(db)
        self.audit = AuditService(db)

    def _next_ticket_number(self) -> str:
        count = self.db.query(Ticket).count()
        return f"INC{count + 1:06d}"

    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        requester_id: int,
        affected_device_id: int | None = None,
        category: str | None = None,
        auto_assign: bool = True,
        actor_id: int | None = None,
    ) -> dict:
        dupes = self.duplicates.find_duplicates(title, description, affected_device_id)
        kb_suggestions = self.kb.suggest_for_ticket(title, description)

        ticket = Ticket(
            ticket_number=self._next_ticket_number(),
            title=title,
            description=description,
            priority=priority,
            requester_id=requester_id,
            affected_device_id=affected_device_id,
            category=category,
            status=TicketStatus.NEW.value,
        )
        self.db.add(ticket)
        self.db.flush()

        self.sla.create_sla(ticket)
        self._record_status(ticket, None, TicketStatus.NEW.value, requester_id, "Ticket created")

        assigned_tech = None
        if auto_assign:
            assigned_tech = self.assignment.assign_best_technician(ticket, category)

        auto_result = self.auto_resolve.try_auto_resolve(ticket)
        if auto_result:
            self.sla.refresh(ticket)
            self.audit.log(
                AuditAction.AUTO_RESOLVE,
                "ticket",
                ticket.id,
                actor_id,
                auto_result,
            )

        self.audit.log(
            AuditAction.CREATE,
            "ticket",
            ticket.id,
            actor_id or requester_id,
            {"title": title, "priority": priority, "duplicates_found": len(dupes)},
        )
        self.db.commit()
        self.db.refresh(ticket)

        return {
            "ticket": ticket,
            "duplicates": dupes,
            "kb_suggestions": kb_suggestions,
            "assigned_technician": assigned_tech,
            "auto_resolve": auto_result,
        }

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        return (
            self.db.query(Ticket)
            .options(
                joinedload(Ticket.sla),
                joinedload(Ticket.requester),
                joinedload(Ticket.assigned_technician),
                joinedload(Ticket.affected_device),
                joinedload(Ticket.work_notes),
                joinedload(Ticket.resolution_doc),
                joinedload(Ticket.status_history),
            )
            .filter(Ticket.id == ticket_id)
            .first()
        )

    def list_tickets(self, status: str | None = None, assigned_to: int | None = None) -> list[Ticket]:
        q = self.db.query(Ticket).options(joinedload(Ticket.sla), joinedload(Ticket.assigned_technician))
        if status:
            q = q.filter(Ticket.status == status)
        if assigned_to:
            q = q.filter(Ticket.assigned_technician_id == assigned_to)
        return q.order_by(Ticket.created_at.desc()).all()

    def update_status(
        self,
        ticket: Ticket,
        new_status: str,
        actor_id: int,
        note: str | None = None,
    ) -> Ticket:
        old = ticket.status
        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()

        if new_status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
            ticket.resolved_at = ticket.resolved_at or datetime.utcnow()
            if new_status == TicketStatus.CLOSED.value:
                ticket.closed_at = datetime.utcnow()

        self._record_status(ticket, old, new_status, actor_id, note)
        self.sla.refresh(ticket)
        self.audit.log(AuditAction.UPDATE, "ticket", ticket.id, actor_id, {"status": f"{old} -> {new_status}"})
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def _record_status(
        self,
        ticket: Ticket,
        from_status: str | None,
        to_status: str,
        user_id: int,
        note: str | None,
    ) -> None:
        entry = TicketStatusHistory(
            ticket_id=ticket.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_id=user_id,
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
