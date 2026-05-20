import enum


class TicketPriority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(str, enum.Enum):
    NEW = "new"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class UserRole(str, enum.Enum):
    END_USER = "end_user"
    TECHNICIAN = "technician"
    TEAM_LEAD = "team_lead"
    ADMIN = "admin"


class SlaStatus(str, enum.Enum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    MET = "met"
    PAUSED = "paused"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    ASSIGN = "assign"
    RESOLVE = "resolve"
    ESCALATE = "escalate"
    COMMENT = "comment"
    AUTO_RESOLVE = "auto_resolve"
    DUPLICATE_LINK = "duplicate_link"
