from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.entities import Ticket, TicketStatusHistory
from app.models.enums import AuditAction, TicketStatus, TimelineEventType
from app.services.assignment_service import AssignmentService
from app.services.audit_service import AuditService
from app.services.auto_resolve_service import AutoResolveService
from app.services.documentation_service import DocumentationService
from app.services.duplicate_service import DuplicateDetectionService
from app.services.kb_service import KnowledgeBaseService
from app.services.priority_service import PriorityService
from app.services.sla_service import SlaService
from app.services.timeline_service import TimelineService
from app.services.workflow_service import WorkflowService


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
        self.timeline = TimelineService(db)
        self.workflow = WorkflowService()
        self.priority = PriorityService()

    def _next_ticket_number(self) -> str:
        count = self.db.query(Ticket).count()
        return f"INC{count + 1:06d}"

    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str | None,
        requester_id: int,
        affected_device_id: int | None = None,
        category: str | None = None,
        ticket_type: str = "incident",
        impact: str = "medium",
        urgency: str = "medium",
        tags: str | None = None,
        auto_assign: bool = True,
        actor_id: int | None = None,
    ) -> dict:
        dupes = self.duplicates.find_duplicates(title, description, affected_device_id)
        kb_suggestions = self.kb.suggest_for_ticket(title, description)

        calculated_priority = priority or self.priority.calculate(impact, urgency)

        ticket = Ticket(
            ticket_number=self._next_ticket_number(),
            title=title,
            description=description,
            priority=calculated_priority,
            requester_id=requester_id,
            affected_device_id=affected_device_id,
            category=category,
            ticket_type=ticket_type,
            impact=impact,
            urgency=urgency,
            tags=tags,
            status=TicketStatus.NEW.value,
        )
        self.db.add(ticket)
        self.db.flush()

        self.sla.create_sla(ticket)
        self._record_status(ticket, None, TicketStatus.NEW.value, requester_id, "Ticket created")
        self.timeline.add_event(
            ticket.id,
            TimelineEventType.CREATED,
            "Ticket opened",
            f"{ticket.ticket_number}: {title}",
            actor_id or requester_id,
            {"priority": calculated_priority, "type": ticket_type, "impact": impact, "urgency": urgency},
        )

        assigned_tech = None
        if auto_assign:
            assigned_tech = self.assignment.assign_best_technician(ticket, category)
            if assigned_tech:
                self.timeline.add_event(
                    ticket.id,
                    TimelineEventType.ASSIGNMENT,
                    f"Assigned to {assigned_tech.display_name}",
                    None,
                    actor_id,
                    {"technician_id": assigned_tech.id},
                )

        auto_result = self.auto_resolve.try_auto_resolve(ticket)
        if auto_result:
            self.sla.refresh(ticket)
            self.timeline.add_event(
                ticket.id,
                TimelineEventType.SYSTEM,
                "Auto-resolved",
                auto_result.get("result", {}).get("message", "Script executed"),
                actor_id,
                auto_result,
            )
            self.audit.log(
                AuditAction.AUTO_RESOLVE,
                "ticket",
                ticket.id,
                actor_id,
                auto_result,
                summary=f"Auto-resolved {ticket.ticket_number}",
            )

        self.audit.log(
            AuditAction.CREATE,
            "ticket",
            ticket.id,
            actor_id or requester_id,
            {"title": title, "priority": calculated_priority, "duplicates_found": len(dupes)},
            summary=f"Created ticket {ticket.ticket_number}",
        )
        self.db.flush()
        self.db.refresh(ticket)

        return {
            "ticket": ticket,
            "duplicates": dupes,
            "kb_suggestions": kb_suggestions,
            "assigned_technician": assigned_tech,
            "auto_resolve": auto_result,
        }

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        ticket = (
            self.db.query(Ticket)
            .options(
                joinedload(Ticket.sla),
                joinedload(Ticket.requester),
                joinedload(Ticket.assigned_technician),
                joinedload(Ticket.affected_device),
                joinedload(Ticket.work_notes),
                joinedload(Ticket.resolution_doc),
                joinedload(Ticket.status_history),
                joinedload(Ticket.timeline_events),
            )
            .filter(Ticket.id == ticket_id)
            .first()
        )
        if ticket:
            self.timeline.backfill_from_ticket(ticket)
        return ticket

    def list_tickets(
        self,
        status: str | None = None,
        assigned_to: int | None = None,
        ticket_type: str | None = None,
        priority: str | None = None,
    ) -> list[Ticket]:
        q = self.db.query(Ticket).options(joinedload(Ticket.sla), joinedload(Ticket.assigned_technician))
        if status:
            q = q.filter(Ticket.status == status)
        if assigned_to:
            q = q.filter(Ticket.assigned_technician_id == assigned_to)
        if ticket_type:
            q = q.filter(Ticket.ticket_type == ticket_type)
        if priority:
            q = q.filter(Ticket.priority == priority)
        return q.order_by(Ticket.created_at.desc()).all()

    def update_status(
        self,
        ticket: Ticket,
        new_status: str,
        actor_id: int,
        note: str | None = None,
        role: str | None = None,
    ) -> Ticket:
        old = ticket.status
        ok, err = self.workflow.can_transition(old, new_status, role, note)
        if not ok:
            raise ValueError(err or "Invalid status transition")

        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()

        if new_status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
            ticket.resolved_at = ticket.resolved_at or datetime.utcnow()
            if new_status == TicketStatus.CLOSED.value:
                ticket.closed_at = datetime.utcnow()
            self.timeline.add_event(
                ticket.id,
                TimelineEventType.RESOLUTION,
                f"Ticket {new_status}",
                note,
                actor_id,
            )

        self._record_status(ticket, old, new_status, actor_id, note)
        self.timeline.add_event(
            ticket.id,
            TimelineEventType.STATUS,
            f"Status: {old} → {new_status}",
            note,
            actor_id,
            {"from": old, "to": new_status},
        )
        self.sla.refresh(ticket)
        if ticket.sla and ticket.sla.status in ("at_risk", "breached"):
            self.timeline.add_event(
                ticket.id,
                TimelineEventType.SLA,
                f"SLA {ticket.sla.status.replace('_', ' ')}",
                f"{ticket.sla.percent_remaining:.0f}% time remaining",
                None,
            )
        self.audit.log(
            AuditAction.UPDATE,
            "ticket",
            ticket.id,
            actor_id,
            {"status": f"{old} -> {new_status}"},
            summary=f"{ticket.ticket_number} status → {new_status}",
        )
        self.db.flush()
        self.db.refresh(ticket)
        return ticket

    def escalate(
        self,
        ticket: Ticket,
        actor_id: int,
        reason: str,
    ) -> Ticket:
        ticket.escalation_level = (ticket.escalation_level or 0) + 1
        ticket.escalated_at = datetime.utcnow()
        ticket.updated_at = datetime.utcnow()

        if ticket.priority == "low":
            ticket.priority = "medium"
        elif ticket.priority == "medium":
            ticket.priority = "high"
        elif ticket.priority == "high":
            ticket.priority = "critical"

        self.sla.refresh(ticket)
        self.timeline.add_event(
            ticket.id,
            TimelineEventType.ESCALATION,
            f"Escalated to Level {ticket.escalation_level}",
            reason,
            actor_id,
            {"level": ticket.escalation_level, "new_priority": ticket.priority},
        )
        self.audit.log(
            AuditAction.ESCALATE,
            "ticket",
            ticket.id,
            actor_id,
            {"level": ticket.escalation_level, "reason": reason},
            summary=f"{ticket.ticket_number} escalated to L{ticket.escalation_level}",
            severity="warning",
        )
        self.db.flush()
        self.db.refresh(ticket)
        return ticket

    def record_satisfaction(
        self,
        ticket: Ticket,
        rating: int,
        comment: str | None,
        actor_id: int,
    ) -> Ticket:
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
        ticket.satisfaction_rating = rating
        ticket.satisfaction_comment = comment
        ticket.updated_at = datetime.utcnow()
        self.timeline.add_event(
            ticket.id,
            TimelineEventType.COMMENT,
            f"Customer satisfaction: {rating}/5",
            comment,
            actor_id,
            {"rating": rating},
        )
        self.audit.log(
            AuditAction.UPDATE,
            "ticket",
            ticket.id,
            actor_id,
            {"satisfaction_rating": rating},
            summary=f"{ticket.ticket_number} CSAT {rating}/5",
        )
        self.db.flush()
        return ticket

    def assign(
        self,
        ticket: Ticket,
        technician_id: int,
        actor_id: int,
    ) -> None:
        tech = self.assignment.manual_assign(ticket, technician_id)
        if tech:
            self.timeline.add_event(
                ticket.id,
                TimelineEventType.ASSIGNMENT,
                f"Reassigned to {tech.display_name}",
                None,
                actor_id,
                {"technician_id": tech.id},
            )
            self.audit.log(
                AuditAction.ASSIGN,
                "ticket",
                ticket.id,
                actor_id,
                {"technician_id": tech.id},
                summary=f"{ticket.ticket_number} assigned to {tech.display_name}",
            )

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
