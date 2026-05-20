import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session, joinedload

from app.models.entities import AuditLog, User
from app.models.enums import AuditAction


class AuditService:
    def __init__(self, db: Session, request: Request | None = None):
        self.db = db
        self.request = request

    def _client_ip(self) -> str | None:
        if not self.request:
            return None
        forwarded = self.request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if self.request.client:
            return self.request.client.host
        return None

    def _request_path(self) -> str | None:
        if self.request:
            return str(self.request.url.path)
        return None

    def log(
        self,
        action: AuditAction | str,
        entity_type: str,
        entity_id: int | None = None,
        actor_id: int | None = None,
        details: dict[str, Any] | str | None = None,
        summary: str | None = None,
        severity: str = "info",
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
            summary=summary,
            severity=severity,
            details=details_str,
            ip_address=ip_address or self._client_ip(),
            request_path=self._request_path(),
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_recent(
        self,
        limit: int = 100,
        entity_type: str | None = None,
        action: str | None = None,
        severity: str | None = None,
        actor_id: int | None = None,
    ) -> list[AuditLog]:
        q = (
            self.db.query(AuditLog)
            .options(joinedload(AuditLog.actor))
            .order_by(AuditLog.created_at.desc())
        )
        if entity_type:
            q = q.filter(AuditLog.entity_type == entity_type)
        if action:
            q = q.filter(AuditLog.action == action)
        if severity:
            q = q.filter(AuditLog.severity == severity)
        if actor_id:
            q = q.filter(AuditLog.actor_id == actor_id)
        return q.limit(limit).all()

    def get_for_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .options(joinedload(AuditLog.actor))
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .all()
        )
