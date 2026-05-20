import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import Ticket
from app.models.enums import TicketStatus


class DuplicateDetectionService:
    def __init__(self, db: Session):
        self.db = db

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return re.sub(r"\s+", " ", text)

    def similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, self._normalize(a), self._normalize(b)).ratio()

    def find_duplicates(
        self,
        title: str,
        description: str,
        device_id: int | None = None,
        exclude_ticket_id: int | None = None,
        limit: int = 5,
    ) -> list[tuple[Ticket, float]]:
        open_statuses = [
            TicketStatus.NEW.value,
            TicketStatus.OPEN.value,
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.PENDING.value,
        ]
        q = self.db.query(Ticket).filter(Ticket.status.in_(open_statuses))
        if device_id:
            q = q.filter(Ticket.affected_device_id == device_id)
        if exclude_ticket_id:
            q = q.filter(Ticket.id != exclude_ticket_id)

        candidates = q.order_by(Ticket.created_at.desc()).limit(100).all()
        combined_new = f"{title} {description}"
        results: list[tuple[Ticket, float]] = []

        for ticket in candidates:
            combined_existing = f"{ticket.title} {ticket.description}"
            score = self.similarity(combined_new, combined_existing)
            if score >= settings.duplicate_similarity_threshold:
                results.append((ticket, round(score, 3)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def link_duplicate(self, ticket: Ticket, master_ticket_id: int) -> Ticket | None:
        master = self.db.query(Ticket).filter(Ticket.id == master_ticket_id).first()
        if not master:
            return None
        ticket.duplicate_of_id = master.id
        ticket.status = TicketStatus.CANCELLED.value
        self.db.flush()
        return master
