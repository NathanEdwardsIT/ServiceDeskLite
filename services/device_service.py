from sqlalchemy.orm import Session

from app.models.entities import Device, Ticket


class DeviceService:
    def __init__(self, db: Session):
        self.db = db

    def get_by_hostname(self, hostname: str) -> Device | None:
        return self.db.query(Device).filter(Device.hostname == hostname).first()

    def get_history(self, device_id: int, limit: int = 20) -> list[Ticket]:
        return (
            self.db.query(Ticket)
            .filter(Ticket.affected_device_id == device_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .all()
        )

    def device_summary(self, device_id: int) -> dict:
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {}
        tickets = self.get_history(device_id, limit=50)
        open_count = sum(1 for t in tickets if t.status not in ("resolved", "closed", "cancelled"))
        return {
            "device": device,
            "total_tickets": len(tickets),
            "open_tickets": open_count,
            "recent_tickets": tickets[:10],
        }
