"""REST API for ticket management — JSON endpoints alongside HTML UI."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.rbac import can_view_ticket, user_has_permission
from app.database import get_db
from app.dependencies import require_login
from app.models.entities import Ticket, User
from app.models.enums import TicketStatus
from app.services.sla_service import SlaService
from app.services.ticket_queue_service import TicketQueueService
from app.services.ticket_service import TicketService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets API"])


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5)
    priority: str | None = None
    category: str | None = None
    ticket_type: str = "incident"
    impact: str = "medium"
    urgency: str = "medium"
    tags: str | None = None
    affected_device_id: int | None = None


class TicketStatusUpdate(BaseModel):
    status: str
    note: str | None = None


class TicketAssign(BaseModel):
    technician_id: int


class TicketEscalate(BaseModel):
    reason: str = Field(..., min_length=5)


class TicketSatisfaction(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


def _ticket_json(ticket: Ticket, sla_svc: SlaService | None = None) -> dict:
    sla_data = None
    if ticket.sla and sla_svc:
        sla_svc.refresh(ticket)
        sla_data = sla_svc.format_timer_display(ticket.sla)
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "category": ticket.category,
        "ticket_type": ticket.ticket_type,
        "impact": ticket.impact,
        "urgency": ticket.urgency,
        "tags": ticket.tags,
        "escalation_level": ticket.escalation_level or 0,
        "requester": ticket.requester.display_name if ticket.requester else None,
        "assigned_to": ticket.assigned_technician.display_name if ticket.assigned_technician else None,
        "assigned_technician_id": ticket.assigned_technician_id,
        "sla": sla_data,
        "satisfaction_rating": ticket.satisfaction_rating,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


def _check_view(user: User, ticket: Ticket) -> None:
    if not can_view_ticket(user.role, user.id, ticket.requester_id, ticket.assigned_technician_id):
        raise HTTPException(403, "Access denied")


@router.get("")
def list_tickets_api(
    q: str = "",
    status: str = "",
    priority: str = "",
    ticket_type: str = "",
    category: str = "",
    assigned_to: int | None = None,
    escalated_only: bool = False,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    view_all = user_has_permission(user, "ticket:view_all")
    result = TicketQueueService(db).search_tickets(
        query=q or None,
        status=status or None,
        priority=priority or None,
        ticket_type=ticket_type or None,
        category=category or None,
        assigned_to=assigned_to,
        escalated_only=escalated_only,
        sort=sort,
        page=page,
        per_page=per_page,
        user_scope=(user.id, view_all),
    )
    sla_svc = SlaService(db)
    db.commit()
    return {
        "total": result["total"],
        "page": result["page"],
        "pages": result["pages"],
        "per_page": result["per_page"],
        "tickets": [_ticket_json(t, sla_svc) for t in result["items"]],
    }


@router.get("/kanban")
def kanban_api(user: User = Depends(require_login), db: Session = Depends(get_db)):
    view_all = user_has_permission(user, "ticket:view_all")
    board = TicketQueueService(db).kanban_board(user_scope=(user.id, view_all))
    db.commit()
    return board


@router.get("/stats")
def queue_stats_api(user: User = Depends(require_login), db: Session = Depends(get_db)):
    svc = TicketService(db)
    view_all = user_has_permission(user, "ticket:view_all")
    if view_all:
        tickets = svc.list_tickets()
    else:
        tickets = [
            t
            for t in svc.list_tickets()
            if t.requester_id == user.id or t.assigned_technician_id == user.id
        ]
    stats = TicketQueueService(db).queue_stats(tickets)
    db.commit()
    return stats


@router.get("/workflow")
def workflow_api():
    wf = WorkflowService()
    return {
        "transitions": {
            s.value: wf.allowed_transitions(s.value)
            for s in TicketStatus
            if s.value != "cancelled"
        },
        "kanban_columns": wf.kanban_columns(),
    }


@router.post("", status_code=201)
def create_ticket_api(
    body: TicketCreate,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not user_has_permission(user, "ticket:create"):
        raise HTTPException(403)
    result = TicketService(db).create_ticket(
        title=body.title,
        description=body.description,
        priority=body.priority,
        requester_id=user.id,
        affected_device_id=body.affected_device_id,
        category=body.category,
        ticket_type=body.ticket_type,
        impact=body.impact,
        urgency=body.urgency,
        tags=body.tags,
        actor_id=user.id,
    )
    db.commit()
    return _ticket_json(result["ticket"], SlaService(db))


@router.get("/{ticket_id}")
def get_ticket_api(ticket_id: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    ticket = TicketService(db).get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404)
    _check_view(user, ticket)
    sla_svc = SlaService(db)
    wf = WorkflowService()
    db.commit()
    data = _ticket_json(ticket, sla_svc)
    data["allowed_transitions"] = wf.allowed_transitions(ticket.status, user.role)
    return data


@router.patch("/{ticket_id}/status")
def update_status_api(
    ticket_id: int,
    body: TicketStatusUpdate,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not user_has_permission(user, "ticket:update"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    _check_view(user, ticket)
    try:
        TicketService(db).update_status(ticket, body.status, user.id, body.note, user.role)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    return _ticket_json(ticket, SlaService(db))


@router.post("/{ticket_id}/assign")
def assign_api(
    ticket_id: int,
    body: TicketAssign,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not user_has_permission(user, "ticket:assign"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    TicketService(db).assign(ticket, body.technician_id, user.id)
    db.commit()
    return _ticket_json(ticket, SlaService(db))


@router.post("/{ticket_id}/escalate")
def escalate_api(
    ticket_id: int,
    body: TicketEscalate,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not user_has_permission(user, "ticket:update"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    ticket = TicketService(db).escalate(ticket, user.id, body.reason)
    db.commit()
    return _ticket_json(ticket, SlaService(db))


@router.post("/{ticket_id}/satisfaction")
def satisfaction_api(
    ticket_id: int,
    body: TicketSatisfaction,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    if ticket.requester_id != user.id and not user_has_permission(user, "ticket:view_all"):
        raise HTTPException(403)
    ticket = TicketService(db).record_satisfaction(ticket, body.rating, body.comment, user.id)
    db.commit()
    return _ticket_json(ticket, SlaService(db))
