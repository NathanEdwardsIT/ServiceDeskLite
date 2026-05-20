import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Ticket, TicketStatusHistory, TicketTimelineEvent, TicketWorkNote
from app.models.enums import TimelineEventType


class TimelineService:
    def __init__(self, db: Session):
        self.db = db

    def add_event(
        self,
        ticket_id: int,
        event_type: TimelineEventType | str,
        title: str,
        description: str | None = None,
        actor_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TicketTimelineEvent:
        evt = TicketTimelineEvent(
            ticket_id=ticket_id,
            event_type=event_type.value if isinstance(event_type, TimelineEventType) else event_type,
            title=title,
            description=description,
            actor_id=actor_id,
            metadata_json=json.dumps(metadata, default=str) if metadata else None,
        )
        self.db.add(evt)
        self.db.flush()
        return evt

    def get_timeline(self, ticket_id: int) -> list[dict[str, Any]]:
        events = (
            self.db.query(TicketTimelineEvent)
            .filter(TicketTimelineEvent.ticket_id == ticket_id)
            .order_by(TicketTimelineEvent.created_at.asc())
            .all()
        )
        result = []
        for e in events:
            meta = {}
            if e.metadata_json:
                try:
                    meta = json.loads(e.metadata_json)
                except json.JSONDecodeError:
                    pass
            result.append(
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "title": e.title,
                    "description": e.description,
                    "actor": e.actor.display_name if e.actor else "System",
                    "created_at": e.created_at,
                    "metadata": meta,
                }
            )
        return result

    def backfill_from_ticket(self, ticket: Ticket) -> None:
        """Populate timeline from legacy status history if empty."""
        if ticket.timeline_events:
            return
        for h in sorted(ticket.status_history, key=lambda x: x.created_at):
            self.add_event(
                ticket.id,
                TimelineEventType.STATUS,
                f"Status → {h.to_status.replace('_', ' ').title()}",
                h.note,
                h.changed_by_id,
                {"from": h.from_status, "to": h.to_status},
            )
        for n in ticket.work_notes:
            self.add_event(
                ticket.id,
                TimelineEventType.COMMENT,
                f"Work note ({n.note_type})",
                n.content[:500],
                n.author_id,
            )
