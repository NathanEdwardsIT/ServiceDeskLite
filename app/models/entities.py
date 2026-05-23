from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import (
    AuditAction,
    SlaStatus,
    TicketPriority,
    TicketStatus,
    UserRole,
)


class ADOrganizationalUnit(Base):
    """Simulated Active Directory OU structure."""

    __tablename__ = "ad_ous"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    distinguished_name: Mapped[str] = mapped_column(String(512), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("ad_ous.id"))

    parent: Mapped["ADOrganizationalUnit | None"] = relationship(remote_side=[id])
    groups: Mapped[list["ADGroup"]] = relationship(back_populates="ou")


class ADGroup(Base):
    __tablename__ = "ad_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    distinguished_name: Mapped[str] = mapped_column(String(512), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    ou_id: Mapped[int | None] = mapped_column(ForeignKey("ad_ous.id"))
    group_type: Mapped[str] = mapped_column(String(32), default="security")
    mapped_role: Mapped[str | None] = mapped_column(String(32))
    role_priority: Mapped[int] = mapped_column(Integer, default=0)

    ou: Mapped["ADOrganizationalUnit | None"] = relationship(back_populates="groups")
    members: Mapped[list["User"]] = relationship(
        secondary="user_ad_groups", back_populates="ad_groups"
    )
    permissions: Mapped[list["ADGroupPermission"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class ADGroupPermission(Base):
    """Extra app permissions granted by group membership (Azure-style app roles)."""

    __tablename__ = "ad_group_permissions"
    __table_args__ = (UniqueConstraint("group_id", "permission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("ad_groups.id"))
    permission: Mapped[str] = mapped_column(String(64))

    group: Mapped["ADGroup"] = relationship(back_populates="permissions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default=UserRole.END_USER.value)
    department: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ad_sam_account: Mapped[str | None] = mapped_column(String(64), unique=True)
    ad_upn: Mapped[str | None] = mapped_column(String(255), unique=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    job_title: Mapped[str | None] = mapped_column(String(128))
    role_sync_from_groups: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    account_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    manager: Mapped["User | None"] = relationship(remote_side=[id])
    ad_groups: Mapped[list["ADGroup"]] = relationship(
        secondary="user_ad_groups", back_populates="members"
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assigned_technician",
        foreign_keys="Ticket.assigned_technician_id",
    )
    created_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="requester",
        foreign_keys="Ticket.requester_id",
    )


class UserADGroup(Base):
    __tablename__ = "user_ad_groups"
    __table_args__ = (UniqueConstraint("user_id", "group_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("ad_groups.id"), primary_key=True)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    asset_tag: Mapped[str | None] = mapped_column(String(64), unique=True)
    device_type: Mapped[str] = mapped_column(String(64))
    manufacturer: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str | None] = mapped_column(String(128), unique=True)
    os: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="in_stock")
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime)
    warranty_expires: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    assigned_user: Mapped["User | None"] = relationship()
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="affected_device")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default=TicketPriority.MEDIUM.value)
    status: Mapped[str] = mapped_column(String(32), default=TicketStatus.NEW.value)
    category: Mapped[str | None] = mapped_column(String(64))
    ticket_type: Mapped[str] = mapped_column(String(32), default="incident")
    impact: Mapped[str] = mapped_column(String(16), default="medium")
    urgency: Mapped[str] = mapped_column(String(16), default="medium")
    tags: Mapped[str | None] = mapped_column(String(512))
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    affected_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    kb_article_id: Mapped[int | None] = mapped_column(ForeignKey("kb_articles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime)
    satisfaction_rating: Mapped[int | None] = mapped_column(Integer)
    satisfaction_comment: Mapped[str | None] = mapped_column(Text)

    requester: Mapped["User"] = relationship(
        back_populates="created_tickets", foreign_keys=[requester_id]
    )
    assigned_technician: Mapped["User | None"] = relationship(
        back_populates="assigned_tickets", foreign_keys=[assigned_technician_id]
    )
    affected_device: Mapped["Device | None"] = relationship(back_populates="tickets")
    duplicate_of: Mapped["Ticket | None"] = relationship(remote_side=[id])
    sla: Mapped["TicketSla | None"] = relationship(
        back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )
    work_notes: Mapped[list["TicketWorkNote"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    resolution_doc: Mapped["ResolutionDocumentation | None"] = relationship(
        back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )
    status_history: Mapped[list["TicketStatusHistory"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    timeline_events: Mapped[list["TicketTimelineEvent"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketTimelineEvent.created_at"
    )
    provisioning: Mapped["ProvisioningRequest | None"] = relationship(
        back_populates="onboarding_ticket", uselist=False
    )


class TicketSla(Base):
    __tablename__ = "ticket_slas"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True)
    target_minutes: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime)
    paused_minutes: Mapped[int] = mapped_column(Integer, default=0)
    breached_at: Mapped[datetime | None] = mapped_column(DateTime)
    met_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default=SlaStatus.ON_TRACK.value)
    percent_remaining: Mapped[float] = mapped_column(Float, default=100.0)

    ticket: Mapped["Ticket"] = relationship(back_populates="sla")


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="status_history")
    changed_by: Mapped["User"] = relationship()


class TicketWorkNote(Base):
    """Internal technician documentation during ticket lifecycle."""

    __tablename__ = "ticket_work_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note_type: Mapped[str] = mapped_column(String(32))  # investigation, action, escalation
    content: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="work_notes")
    author: Mapped["User"] = relationship()


class ResolutionDocumentation(Base):
    """Formal resolution documentation for knowledge transfer and audits."""

    __tablename__ = "resolution_documentation"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    root_cause: Mapped[str] = mapped_column(Text)
    resolution_steps: Mapped[str] = mapped_column(Text)
    prevention_notes: Mapped[str | None] = mapped_column(Text)
    systems_affected: Mapped[str | None] = mapped_column(Text)
    verification_steps: Mapped[str | None] = mapped_column(Text)
    time_spent_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="resolution_doc")
    author: Mapped["User"] = relationship()


class KBArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[str | None] = mapped_column(String(512))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    author: Mapped["User"] = relationship()


class TicketTimelineEvent(Base):
    """Unified incident timeline — all ticket lifecycle events in one stream."""

    __tablename__ = "ticket_timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="timeline_events")
    actor: Mapped["User | None"] = relationship()


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reason: Mapped[str | None] = mapped_column(Text)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    temporary_password_hint: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    target_user: Mapped["User"] = relationship(foreign_keys=[target_user_id])
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_id])
    ticket: Mapped["Ticket | None"] = relationship()


class ProvisioningRequest(Base):
    __tablename__ = "provisioning_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    department: Mapped[str] = mapped_column(String(128))
    job_title: Mapped[str] = mapped_column(String(128))
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    created_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    onboarding_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), unique=True)
    generated_username: Mapped[str | None] = mapped_column(String(64))
    generated_email: Mapped[str | None] = mapped_column(String(255))
    group_ids_json: Mapped[str | None] = mapped_column(Text)
    steps_json: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_user: Mapped["User | None"] = relationship(foreign_keys=[created_user_id])
    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_id])
    assigned_device: Mapped["Device | None"] = relationship()
    onboarding_ticket: Mapped["Ticket | None"] = relationship(back_populates="provisioning")
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    request_path: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    actor: Mapped["User | None"] = relationship()


class AutoResolveScript(Base):
    __tablename__ = "auto_resolve_scripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text)
    trigger_keywords: Mapped[str] = mapped_column(String(512))
    script_path: Mapped[str] = mapped_column(String(255))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
