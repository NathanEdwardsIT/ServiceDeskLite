"""Apply AD schema updates and seed group role mappings on existing databases."""

from app.auth.rbac import all_permission_keys
from app.database import SessionLocal, init_db
from app.models.entities import ADGroup, ADGroupPermission
from app.models.enums import UserRole
from app.services.ad_management_service import ADManagementService

GROUP_DEFAULTS = {
    "IT-Helpdesk": (UserRole.TECHNICIAN.value, 10, ["ticket:assign", "kb:write"]),
    "IT-Team-Leads": (UserRole.TEAM_LEAD.value, 20, ["dashboard:performance", "audit:view", "ad:view"]),
    "IT-Admins": (UserRole.ADMIN.value, 30, ["ad:manage", "users:manage", "scripts:manage"]),
}


def migrate():
    init_db()
    db = SessionLocal()
    valid = set(all_permission_keys())

    for name, (role, priority, perms) in GROUP_DEFAULTS.items():
        g = db.query(ADGroup).filter(ADGroup.name == name).first()
        if not g:
            continue
        g.mapped_role = g.mapped_role or role
        g.role_priority = priority
        existing = {p.permission for p in g.permissions}
        for perm in perms:
            if perm in valid and perm not in existing:
                db.add(ADGroupPermission(group_id=g.id, permission=perm))

    ADManagementService(db).sync_all_roles()
    db.commit()
    print("AD migration complete: group roles, permissions, and user sync applied.")
    db.close()


if __name__ == "__main__":
    migrate()
