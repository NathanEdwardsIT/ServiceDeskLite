from sqlalchemy.orm import Session

from app.models.entities import ResolutionDocumentation, Ticket, TicketWorkNote
from app.models.enums import AuditAction


class DocumentationService:
    def __init__(self, db: Session):
        self.db = db

    def add_work_note(
        self,
        ticket_id: int,
        author_id: int,
        content: str,
        note_type: str = "investigation",
        is_internal: bool = True,
    ) -> TicketWorkNote:
        note = TicketWorkNote(
            ticket_id=ticket_id,
            author_id=author_id,
            note_type=note_type,
            content=content,
            is_internal=is_internal,
        )
        self.db.add(note)
        self.db.flush()
        return note

    def get_work_notes(self, ticket_id: int, include_internal: bool = True) -> list[TicketWorkNote]:
        q = self.db.query(TicketWorkNote).filter(TicketWorkNote.ticket_id == ticket_id)
        if not include_internal:
            q = q.filter(TicketWorkNote.is_internal.is_(False))
        return q.order_by(TicketWorkNote.created_at.asc()).all()

    def create_resolution_doc(
        self,
        ticket: Ticket,
        author_id: int,
        root_cause: str,
        resolution_steps: str,
        prevention_notes: str | None = None,
        systems_affected: str | None = None,
        verification_steps: str | None = None,
        time_spent_minutes: int | None = None,
    ) -> ResolutionDocumentation:
        if ticket.resolution_doc:
            doc = ticket.resolution_doc
            doc.root_cause = root_cause
            doc.resolution_steps = resolution_steps
            doc.prevention_notes = prevention_notes
            doc.systems_affected = systems_affected
            doc.verification_steps = verification_steps
            doc.time_spent_minutes = time_spent_minutes
        else:
            doc = ResolutionDocumentation(
                ticket_id=ticket.id,
                author_id=author_id,
                root_cause=root_cause,
                resolution_steps=resolution_steps,
                prevention_notes=prevention_notes,
                systems_affected=systems_affected,
                verification_steps=verification_steps,
                time_spent_minutes=time_spent_minutes,
            )
            self.db.add(doc)
        self.db.flush()
        return doc

    def ticket_documentation_bundle(self, ticket: Ticket) -> dict:
        return {
            "work_notes": ticket.work_notes,
            "resolution": ticket.resolution_doc,
            "status_history": ticket.status_history,
        }
