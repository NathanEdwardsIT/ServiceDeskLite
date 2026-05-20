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


class TicketType(str, enum.Enum):
    INCIDENT = "incident"
    REQUEST = "request"
    PROBLEM = "problem"
    ONBOARDING = "onboarding"
    CHANGE = "change"


class TicketImpact(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TimelineEventType(str, enum.Enum):
    CREATED = "created"
    STATUS = "status"
    ASSIGNMENT = "assignment"
    COMMENT = "comment"
    SLA = "sla"
    ESCALATION = "escalation"
    RESOLUTION = "resolution"
    SYSTEM = "system"
    LINK = "link"


class DeviceStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    DEPLOYED = "deployed"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class PasswordResetStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ProvisioningStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    PROVISION = "provision"
    PASSWORD_RESET = "password_reset"
    DEVICE_ASSIGN = "device_assign"
    APPROVE = "approve"
    REJECT = "reject"
