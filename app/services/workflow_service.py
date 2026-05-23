"""ITIL-aligned ticket workflow engine with validated state transitions."""

from app.models.enums import TicketStatus, UserRole

# Valid transitions: current_status -> {allowed next statuses}
_TRANSITIONS: dict[str, set[str]] = {
    TicketStatus.NEW.value: {TicketStatus.OPEN.value, TicketStatus.CANCELLED.value},
    TicketStatus.OPEN.value: {
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.PENDING.value,
        TicketStatus.CANCELLED.value,
    },
    TicketStatus.IN_PROGRESS.value: {
        TicketStatus.PENDING.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.OPEN.value,
    },
    TicketStatus.PENDING.value: {
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.OPEN.value,
        TicketStatus.RESOLVED.value,
    },
    TicketStatus.RESOLVED.value: {TicketStatus.CLOSED.value, TicketStatus.IN_PROGRESS.value},
    TicketStatus.CLOSED.value: {TicketStatus.IN_PROGRESS.value},
    TicketStatus.CANCELLED.value: set(),
}

# Transitions requiring a status-change note
_REQUIRES_NOTE: set[tuple[str, str]] = {
    (TicketStatus.RESOLVED.value, TicketStatus.IN_PROGRESS.value),
    (TicketStatus.CLOSED.value, TicketStatus.IN_PROGRESS.value),
    (TicketStatus.IN_PROGRESS.value, TicketStatus.PENDING.value),
    (TicketStatus.OPEN.value, TicketStatus.PENDING.value),
    (TicketStatus.NEW.value, TicketStatus.CANCELLED.value),
}


class WorkflowService:
    """Ticket lifecycle state machine."""

    def allowed_transitions(self, current_status: str, role: str | None = None) -> list[str]:
        return sorted(_TRANSITIONS.get(current_status, set()))

    def can_transition(
        self,
        from_status: str,
        to_status: str,
        role: str | None = None,
        note: str | None = None,
    ) -> tuple[bool, str | None]:
        """Return (ok, error_message)."""
        if from_status == to_status:
            return True, None

        allowed = _TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            return False, f"Cannot transition from '{from_status}' to '{to_status}'"

        if (from_status, to_status) in _REQUIRES_NOTE and not (note and note.strip()):
            return False, "This transition requires a note explaining the reason"

        return True, None

    def requires_note(self, from_status: str, to_status: str) -> bool:
        return (from_status, to_status) in _REQUIRES_NOTE

    def kanban_columns(self) -> list[dict]:
        """Kanban board column definitions."""
        return [
            {"id": TicketStatus.NEW.value, "label": "New", "color": "#1e40af"},
            {"id": TicketStatus.OPEN.value, "label": "Open", "color": "#2563eb"},
            {"id": TicketStatus.IN_PROGRESS.value, "label": "In Progress", "color": "#7c3aed"},
            {"id": TicketStatus.PENDING.value, "label": "Pending", "color": "#d97706"},
            {"id": TicketStatus.RESOLVED.value, "label": "Resolved", "color": "#059669"},
        ]
