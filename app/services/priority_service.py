"""ITIL priority matrix — derive priority from impact × urgency."""

from app.models.enums import TicketPriority

_MATRIX: dict[tuple[str, str], str] = {
    ("critical", "critical"): TicketPriority.CRITICAL.value,
    ("critical", "high"): TicketPriority.CRITICAL.value,
    ("critical", "medium"): TicketPriority.HIGH.value,
    ("critical", "low"): TicketPriority.MEDIUM.value,
    ("high", "critical"): TicketPriority.CRITICAL.value,
    ("high", "high"): TicketPriority.HIGH.value,
    ("high", "medium"): TicketPriority.HIGH.value,
    ("high", "low"): TicketPriority.MEDIUM.value,
    ("medium", "critical"): TicketPriority.HIGH.value,
    ("medium", "high"): TicketPriority.MEDIUM.value,
    ("medium", "medium"): TicketPriority.MEDIUM.value,
    ("medium", "low"): TicketPriority.LOW.value,
    ("low", "critical"): TicketPriority.MEDIUM.value,
    ("low", "high"): TicketPriority.LOW.value,
    ("low", "medium"): TicketPriority.LOW.value,
    ("low", "low"): TicketPriority.LOW.value,
}

_IMPACT_LABELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_URGENCY_LABELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class PriorityService:
    """Calculate ticket priority from business impact and urgency."""

    @staticmethod
    def calculate(impact: str, urgency: str) -> str:
        impact = (impact or "medium").lower()
        urgency = (urgency or "medium").lower()
        return _MATRIX.get((impact, urgency), TicketPriority.MEDIUM.value)

    @staticmethod
    def matrix_rows() -> list[dict]:
        """Return full matrix for UI display."""
        rows = []
        for impact in ("low", "medium", "high", "critical"):
            cells = []
            for urgency in ("low", "medium", "high", "critical"):
                cells.append(
                    {
                        "impact": impact,
                        "urgency": urgency,
                        "priority": PriorityService.calculate(impact, urgency),
                    }
                )
            rows.append({"impact": impact, "cells": cells})
        return rows

    @staticmethod
    def score(impact: str, urgency: str) -> int:
        """Numeric score for sorting (higher = more urgent)."""
        i = _IMPACT_LABELS.get((impact or "medium").lower(), 2)
        u = _URGENCY_LABELS.get((urgency or "medium").lower(), 2)
        return i * 10 + u
