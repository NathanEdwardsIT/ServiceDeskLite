from app.models.entities import User
from app.models.enums import UserRole

ROLE_HIERARCHY = {
    UserRole.END_USER: 0,
    UserRole.TECHNICIAN: 1,
    UserRole.TEAM_LEAD: 2,
    UserRole.ADMIN: 3,
}

PERMISSIONS = {
    "ticket:create": {UserRole.END_USER, UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:view_own": {UserRole.END_USER, UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:view_all": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:assign": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:update": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:resolve": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ticket:work_note": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "kb:read": {UserRole.END_USER, UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "kb:write": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "dashboard:performance": {UserRole.TEAM_LEAD, UserRole.ADMIN},
    "audit:view": {UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ad:view": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "ad:manage": {UserRole.ADMIN},
    "users:manage": {UserRole.ADMIN},
    "scripts:manage": {UserRole.ADMIN},
    "devices:view": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "devices:manage": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "password_reset:request": {UserRole.END_USER, UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "password_reset:approve": {UserRole.TECHNICIAN, UserRole.TEAM_LEAD, UserRole.ADMIN},
    "provisioning:manage": {UserRole.TEAM_LEAD, UserRole.ADMIN},
}

PERMISSION_LABELS = {
    "ticket:create": "Create tickets",
    "ticket:view_own": "View own tickets",
    "ticket:view_all": "View all tickets",
    "ticket:assign": "Assign tickets",
    "ticket:update": "Update ticket status",
    "ticket:resolve": "Resolve tickets",
    "ticket:work_note": "Add work notes",
    "kb:read": "Read knowledge base",
    "kb:write": "Edit knowledge base",
    "dashboard:performance": "View performance dashboard",
    "audit:view": "View audit log",
    "ad:view": "Browse directory",
    "ad:manage": "Manage directory (users/groups/OUs)",
    "users:manage": "Manage application users",
    "scripts:manage": "Manage auto-resolve scripts",
    "devices:view": "View device inventory",
    "devices:manage": "Manage device inventory",
    "password_reset:request": "Request password resets",
    "password_reset:approve": "Approve and execute password resets",
    "provisioning:manage": "Run employee provisioning workflows",
}

ROLE_LABELS = {
    UserRole.END_USER.value: "End User",
    UserRole.TECHNICIAN.value: "Technician",
    UserRole.TEAM_LEAD.value: "Team Lead",
    UserRole.ADMIN.value: "Administrator",
}


def all_permission_keys() -> list[str]:
    return list(PERMISSIONS.keys())


def has_permission(role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(permission, set())
    try:
        user_role = UserRole(role)
    except ValueError:
        return False
    return user_role in allowed


def get_role_permissions(role: str) -> set[str]:
    try:
        user_role = UserRole(role)
    except ValueError:
        return set()
    return {p for p, roles in PERMISSIONS.items() if user_role in roles}


def get_user_permissions(user: User) -> set[str]:
    perms = get_role_permissions(user.role)
    for group in user.ad_groups:
        for gp in group.permissions:
            perms.add(gp.permission)
    return perms


def user_has_permission(user: User, permission: str) -> bool:
    return permission in get_user_permissions(user)


def can_view_ticket(
    role: str,
    user_id: int,
    ticket_requester_id: int,
    assigned_id: int | None,
    user: User | None = None,
) -> bool:
    if user is not None:
        if user_has_permission(user, "ticket:view_all"):
            return True
        if user_has_permission(user, "ticket:view_own"):
            return user_id in (ticket_requester_id, assigned_id)
        return False
    if has_permission(role, "ticket:view_all"):
        return True
    if has_permission(role, "ticket:view_own"):
        return user_id in (ticket_requester_id, assigned_id)
    return False
