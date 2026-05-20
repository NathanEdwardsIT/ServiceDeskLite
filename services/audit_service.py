import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditLog
from app.models.enums import AuditAction


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        action: AuditAction | str,
        entity_type: str,
        entity_id: int | None = None,
        actor_id: int | None = None,
        details: dict[str, Any] | str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        if isinstance(details, dict):
            details_str = json.dumps(details, default=str)
        else:
            details_str = details

        entry = AuditLog(
            actor_id=actor_id,
            action=action.value if isinstance(action, AuditAction) else action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details_str,
            ip_address=ip_address,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_recent(self, limit: int = 50, entity_type: str | None = None) -> list[AuditLog]:
        q = self.db.query(AuditLog).order_by(AuditLog.created_at.desc())
        if entity_type:
            q = q.filter(AuditLog.entity_type == entity_type)
        return q.limit(limit).all()
