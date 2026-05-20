import secrets
import string
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.auth.passwords import hash_password
from app.models.entities import PasswordResetRequest, User
from app.models.enums import AuditAction, PasswordResetStatus, TicketPriority, TicketType
from app.services.ad_management_service import ADManagementService
from app.services.audit_service import AuditService
from app.services.ticket_service import TicketService
from app.services.timeline_service import TimelineService
from app.models.enums import TimelineEventType


class PasswordResetService:
    def __init__(self, db: Session):
        self.db = db

    def list_requests(self, status: str | None = None, limit: int = 50) -> list[PasswordResetRequest]:
        q = (
            self.db.query(PasswordResetRequest)
            .options(
                joinedload(PasswordResetRequest.target_user),
                joinedload(PasswordResetRequest.requested_by),
                joinedload(PasswordResetRequest.approved_by),
            )
            .order_by(PasswordResetRequest.created_at.desc())
        )
        if status:
            q = q.filter(PasswordResetRequest.status == status)
        return q.limit(limit).all()

    def create_request(
        self,
        target_user_id: int,
        requested_by_id: int,
        reason: str | None = None,
        auto_approve: bool = False,
    ) -> PasswordResetRequest:
        req = PasswordResetRequest(
            target_user_id=target_user_id,
            requested_by_id=requested_by_id,
            reason=reason,
            status=PasswordResetStatus.PENDING.value,
        )
        self.db.add(req)
        self.db.flush()

        if auto_approve:
            self.approve(req.id, requested_by_id)
        return req

    def approve(self, request_id: int, approver_id: int) -> PasswordResetRequest:
        req = self._get(request_id)
        req.status = PasswordResetStatus.APPROVED.value
        req.approved_by_id = approver_id
        self.db.flush()
        return req

    def reject(self, request_id: int, approver_id: int) -> PasswordResetRequest:
        req = self._get(request_id)
        req.status = PasswordResetStatus.REJECTED.value
        req.approved_by_id = approver_id
        self.db.flush()
        return req

    def _generate_temp_password(self, length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def complete(self, request_id: int, actor_id: int, create_ticket: bool = True) -> PasswordResetRequest:
        req = self._get(request_id)
        if req.status == PasswordResetStatus.REJECTED.value:
            raise ValueError("Cannot complete a rejected request")

        temp_pw = self._generate_temp_password()
        self._last_temp_password = temp_pw
        target = self.db.query(User).filter(User.id == req.target_user_id).first()
        target.password_hash = hash_password(temp_pw)
        req.temporary_password_hint = temp_pw[:3] + "••••••"
        req.status = PasswordResetStatus.COMPLETED.value
        req.completed_at = datetime.utcnow()
        if not req.approved_by_id:
            req.approved_by_id = actor_id

        ticket = None
        if create_ticket:
            result = TicketService(self.db).create_ticket(
                title=f"Password reset completed for {target.display_name}",
                description=(
                    f"Self-service / help-desk password reset executed.\n"
                    f"User: {target.ad_upn}\nReason: {req.reason or 'Not specified'}"
                ),
                priority=TicketPriority.LOW.value,
                requester_id=req.target_user_id,
                category="access",
                auto_assign=True,
                actor_id=actor_id,
            )
            ticket = result["ticket"]
            ticket.ticket_type = TicketType.REQUEST.value
            req.ticket_id = ticket.id
            TimelineService(self.db).add_event(
                ticket.id,
                TimelineEventType.SYSTEM,
                "Linked password reset",
                f"Reset request #{req.id} completed",
                actor_id,
                {"password_reset_id": req.id},
            )

        self.db.flush()
        return req

    def _get(self, request_id: int) -> PasswordResetRequest:
        req = (
            self.db.query(PasswordResetRequest)
            .filter(PasswordResetRequest.id == request_id)
            .first()
        )
        if not req:
            raise ValueError("Password reset request not found")
        return req
