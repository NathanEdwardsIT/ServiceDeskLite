"""Active Directory management — users, groups, OUs, and permission assignments."""

import re
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.auth.passwords import hash_password
from app.auth.rbac import ROLE_HIERARCHY, all_permission_keys
from app.models.entities import ADGroup, ADGroupPermission, ADOrganizationalUnit, User
from app.models.enums import UserRole

DOMAIN = "corp.local"
DEFAULT_OU_DN = "OU=Users,OU=Corp,DC=corp,DC=local"


class ADManagementService:
    def __init__(self, db: Session):
        self.db = db

    # --- Organizational Units ---

    def list_ous(self) -> list[ADOrganizationalUnit]:
        return self.db.query(ADOrganizationalUnit).order_by(ADOrganizationalUnit.name).all()

    def get_ou_tree(self) -> list[dict[str, Any]]:
        ous = self.list_ous()
        by_id = {
            ou.id: {
                "id": ou.id,
                "name": ou.name,
                "dn": ou.distinguished_name,
                "parent_id": ou.parent_id,
                "children": [],
            }
            for ou in ous
        }
        roots = []
        for ou in ous:
            node = by_id[ou.id]
            if ou.parent_id and ou.parent_id in by_id:
                by_id[ou.parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def create_ou(self, name: str, parent_id: int | None = None) -> ADOrganizationalUnit:
        parent_dn = "DC=corp,DC=local"
        if parent_id:
            parent = self.db.query(ADOrganizationalUnit).filter(ADOrganizationalUnit.id == parent_id).first()
            if parent:
                parent_dn = parent.distinguished_name
        dn = f"OU={name},{parent_dn}"
        ou = ADOrganizationalUnit(name=name, distinguished_name=dn, parent_id=parent_id)
        self.db.add(ou)
        self.db.flush()
        return ou

    def delete_ou(self, ou_id: int) -> bool:
        ou = self.db.query(ADOrganizationalUnit).filter(ADOrganizationalUnit.id == ou_id).first()
        if not ou:
            return False
        if ou.groups:
            raise ValueError("Cannot delete OU that contains groups. Move or delete groups first.")
        children = self.db.query(ADOrganizationalUnit).filter(ADOrganizationalUnit.parent_id == ou_id).count()
        if children:
            raise ValueError("Cannot delete OU with child OUs.")
        self.db.delete(ou)
        self.db.flush()
        return True

    # --- Groups ---

    def list_groups(self, ou_id: int | None = None) -> list[ADGroup]:
        q = self.db.query(ADGroup).options(
            joinedload(ADGroup.ou),
            joinedload(ADGroup.permissions),
            joinedload(ADGroup.members),
        )
        if ou_id:
            q = q.filter(ADGroup.ou_id == ou_id)
        return q.order_by(ADGroup.name).all()

    def get_group(self, group_id: int) -> ADGroup | None:
        return (
            self.db.query(ADGroup)
            .options(
                joinedload(ADGroup.ou),
                joinedload(ADGroup.permissions),
                joinedload(ADGroup.members),
            )
            .filter(ADGroup.id == group_id)
            .first()
        )

    def create_group(
        self,
        name: str,
        description: str | None = None,
        ou_id: int | None = None,
        group_type: str = "security",
        mapped_role: str | None = None,
        role_priority: int = 0,
    ) -> ADGroup:
        ou_dn = DEFAULT_OU_DN
        if ou_id:
            ou = self.db.query(ADOrganizationalUnit).filter(ADOrganizationalUnit.id == ou_id).first()
            if ou:
                ou_dn = ou.distinguished_name
        dn = f"CN={name},{ou_dn}"
        group = ADGroup(
            name=name,
            distinguished_name=dn,
            description=description,
            ou_id=ou_id,
            group_type=group_type,
            mapped_role=mapped_role or None,
            role_priority=role_priority,
        )
        self.db.add(group)
        self.db.flush()
        return group

    def update_group(
        self,
        group: ADGroup,
        name: str | None = None,
        description: str | None = None,
        ou_id: int | None = None,
        group_type: str | None = None,
        mapped_role: str | None = None,
        role_priority: int | None = None,
        clear_mapped_role: bool = False,
    ) -> ADGroup:
        if name and name != group.name:
            group.name = name
        if description is not None:
            group.description = description
        if ou_id is not None:
            group.ou_id = ou_id or None
        if group_type:
            group.group_type = group_type
        if clear_mapped_role:
            group.mapped_role = None
        elif mapped_role is not None:
            group.mapped_role = mapped_role or None
        if role_priority is not None:
            group.role_priority = role_priority
        self.db.flush()
        return group

    def delete_group(self, group_id: int) -> bool:
        group = self.get_group(group_id)
        if not group:
            return False
        self.db.delete(group)
        self.db.flush()
        return True

    def set_group_permissions(self, group_id: int, permission_keys: list[str]) -> ADGroup:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Group not found")
        valid = set(all_permission_keys())
        group.permissions.clear()
        for key in permission_keys:
            if key in valid:
                self.db.add(ADGroupPermission(group_id=group.id, permission=key))
        self.db.flush()
        return group

    def add_user_to_group(self, user_id: int, group_id: int) -> User:
        user = self.get_user(user_id)
        group = self.get_group(group_id)
        if not user or not group:
            raise ValueError("User or group not found")
        if group not in user.ad_groups:
            user.ad_groups.append(group)
        if user.role_sync_from_groups:
            self.sync_user_role(user)
        self.db.flush()
        return user

    def remove_user_from_group(self, user_id: int, group_id: int) -> User:
        user = self.get_user(user_id)
        group = self.get_group(group_id)
        if not user or not group:
            raise ValueError("User or group not found")
        if group in user.ad_groups:
            user.ad_groups.remove(group)
        if user.role_sync_from_groups:
            self.sync_user_role(user)
        self.db.flush()
        return user

    # --- Users ---

    def list_users(
        self,
        query: str | None = None,
        ou_id: int | None = None,
        active_only: bool = False,
        include_all: bool = True,
    ) -> list[User]:
        q = self.db.query(User).options(
            joinedload(User.ad_groups),
            joinedload(User.manager),
        )
        if active_only:
            q = q.filter(User.is_active.is_(True))
        if query:
            pattern = f"%{query}%"
            q = q.filter(
                (User.display_name.ilike(pattern))
                | (User.username.ilike(pattern))
                | (User.email.ilike(pattern))
                | (User.ad_sam_account.ilike(pattern))
            )
        users = q.order_by(User.display_name).all()
        if ou_id:
            group_ids = {g.id for g in self.list_groups(ou_id)}
            users = [u for u in users if any(g.id in group_ids for g in u.ad_groups)]
        return users

    def get_user(self, user_id: int) -> User | None:
        return (
            self.db.query(User)
            .options(
                joinedload(User.ad_groups).joinedload(ADGroup.permissions),
                joinedload(User.manager),
            )
            .filter(User.id == user_id)
            .first()
        )

    def _slug_sam(self, value: str) -> str:
        sam = re.sub(r"[^a-zA-Z0-9._-]", "", value.lower().replace(" ", "."))[:20]
        return sam or "user"

    def _unique_sam(self, base: str) -> str:
        sam = self._slug_sam(base)
        candidate = sam
        n = 1
        while self.db.query(User).filter(User.ad_sam_account == candidate).first():
            candidate = f"{sam}{n}"
            n += 1
        return candidate

    def create_user(
        self,
        display_name: str,
        email: str,
        username: str | None = None,
        password: str = "password",
        department: str | None = None,
        job_title: str | None = None,
        role: str = UserRole.END_USER.value,
        manager_id: int | None = None,
        group_ids: list[int] | None = None,
        role_sync_from_groups: bool = True,
        is_active: bool = True,
    ) -> User:
        sam = self._unique_sam(username or email.split("@")[0])
        uname = username or sam
        if self.db.query(User).filter(User.username == uname).first():
            raise ValueError(f"Username '{uname}' already exists")
        if self.db.query(User).filter(User.email == email).first():
            raise ValueError(f"Email '{email}' already exists")

        user = User(
            username=uname,
            display_name=display_name,
            email=email,
            password_hash=hash_password(password),
            department=department,
            job_title=job_title,
            role=role,
            manager_id=manager_id,
            ad_sam_account=sam,
            ad_upn=f"{sam}@{DOMAIN}",
            role_sync_from_groups=role_sync_from_groups,
            is_active=is_active,
        )
        if group_ids:
            for gid in group_ids:
                g = self.get_group(gid)
                if g:
                    user.ad_groups.append(g)
        self.db.add(user)
        self.db.flush()
        if role_sync_from_groups:
            self.sync_user_role(user)
        self.db.flush()
        return user

    def update_user(
        self,
        user: User,
        display_name: str | None = None,
        email: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
        role: str | None = None,
        manager_id: int | None = None,
        role_sync_from_groups: bool | None = None,
        is_active: bool | None = None,
    ) -> User:
        if display_name:
            user.display_name = display_name
        if email:
            existing = self.db.query(User).filter(User.email == email, User.id != user.id).first()
            if existing:
                raise ValueError("Email already in use")
            user.email = email
        if department is not None:
            user.department = department or None
        if job_title is not None:
            user.job_title = job_title or None
        if role is not None:
            user.role = role
        if manager_id is not None:
            user.manager_id = manager_id or None
        if role_sync_from_groups is not None:
            user.role_sync_from_groups = role_sync_from_groups
        if is_active is not None:
            user.is_active = is_active
        if user.role_sync_from_groups:
            self.sync_user_role(user)
        self.db.flush()
        return user

    def reset_password(self, user_id: int, new_password: str) -> User:
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found")
        user.password_hash = hash_password(new_password)
        self.db.flush()
        return user

    def sync_user_role(self, user: User) -> str:
        """Derive role from highest-priority group with mapped_role."""
        mapped_groups = [
            g for g in user.ad_groups if g.mapped_role and g.mapped_role in ROLE_HIERARCHY
        ]
        if not mapped_groups:
            return user.role

        def sort_key(g: ADGroup):
            try:
                return (g.role_priority, ROLE_HIERARCHY[UserRole(g.mapped_role)])
            except ValueError:
                return (g.role_priority, -1)

        best = max(mapped_groups, key=sort_key)
        user.role = best.mapped_role
        return user.role

    def sync_all_roles(self) -> int:
        count = 0
        users = self.db.query(User).options(joinedload(User.ad_groups)).filter(
            User.role_sync_from_groups.is_(True)
        ).all()
        for user in users:
            self.sync_user_role(user)
            count += 1
        self.db.flush()
        return count

    def user_to_dict(self, user: User) -> dict[str, Any]:
        from app.auth.rbac import get_user_permissions

        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "department": user.department,
            "job_title": user.job_title,
            "role": user.role,
            "is_active": user.is_active,
            "sam": user.ad_sam_account,
            "upn": user.ad_upn,
            "role_sync_from_groups": user.role_sync_from_groups,
            "manager": user.manager.display_name if user.manager else None,
            "manager_id": user.manager_id,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "account_locked": getattr(user, "account_locked", False),
            "groups": [{"id": g.id, "name": g.name} for g in user.ad_groups],
            "effective_permissions": sorted(get_user_permissions(user)),
        }

    def group_to_dict(self, group: ADGroup) -> dict[str, Any]:
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "dn": group.distinguished_name,
            "ou_id": group.ou_id,
            "ou_name": group.ou.name if group.ou else None,
            "group_type": group.group_type,
            "mapped_role": group.mapped_role,
            "role_priority": group.role_priority,
            "member_count": len(group.members),
            "members": [{"id": m.id, "display_name": m.display_name, "email": m.email} for m in group.members],
            "permissions": [p.permission for p in group.permissions],
        }

    def directory_stats(self) -> dict[str, int]:
        return {
            "users": self.db.query(User).count(),
            "active_users": self.db.query(User).filter(User.is_active.is_(True)).count(),
            "disabled_users": self.db.query(User).filter(User.is_active.is_(False)).count(),
            "locked_accounts": self.db.query(User).filter(User.account_locked.is_(True)).count(),
            "groups": self.db.query(ADGroup).count(),
            "ous": self.db.query(ADOrganizationalUnit).count(),
            "departments": self.db.query(User.department).filter(User.department.isnot(None)).distinct().count(),
        }

    def department_breakdown(self) -> list[dict]:
        from sqlalchemy import func

        rows = (
            self.db.query(User.department, func.count(User.id))
            .filter(User.department.isnot(None), User.is_active.is_(True))
            .group_by(User.department)
            .order_by(func.count(User.id).desc())
            .all()
        )
        return [{"department": d or "Unknown", "count": c} for d, c in rows]

    def get_org_chart(self, root_id: int | None = None) -> dict[str, Any]:
        """Build org hierarchy from manager_id relationships."""
        users = (
            self.db.query(User)
            .options(joinedload(User.ad_groups))
            .filter(User.is_active.is_(True))
            .all()
        )
        by_id = {u.id: u for u in users}
        children_map: dict[int | None, list[User]] = {}
        for u in users:
            mid = u.manager_id if u.manager_id in by_id else None
            children_map.setdefault(mid, []).append(u)

        def node(user: User) -> dict:
            kids = sorted(children_map.get(user.id, []), key=lambda x: x.display_name)
            return {
                "id": user.id,
                "name": user.display_name,
                "title": user.job_title or user.role,
                "department": user.department,
                "email": user.email,
                "role": user.role,
                "group_count": len(user.ad_groups),
                "children": [node(c) for c in kids],
            }

        if root_id and root_id in by_id:
            return node(by_id[root_id])

        roots = sorted(children_map.get(None, []), key=lambda x: x.display_name)
        # Users whose manager is inactive/missing also appear at root
        for u in users:
            if u.manager_id and u.manager_id not in by_id and u not in roots:
                roots.append(u)
        return {
            "roots": [node(r) for r in roots],
            "total_nodes": len(users),
        }

    def bulk_set_active(self, user_ids: list[int], is_active: bool) -> int:
        count = 0
        for uid in user_ids:
            user = self.get_user(uid)
            if user:
                user.is_active = is_active
                count += 1
        self.db.flush()
        return count

    def bulk_add_to_group(self, user_ids: list[int], group_id: int) -> int:
        count = 0
        for uid in user_ids:
            try:
                self.add_user_to_group(uid, group_id)
                count += 1
            except ValueError:
                continue
        return count

    def bulk_sync_roles(self, user_ids: list[int]) -> int:
        count = 0
        for uid in user_ids:
            user = self.get_user(uid)
            if user and user.role_sync_from_groups:
                self.sync_user_role(user)
                count += 1
        self.db.flush()
        return count

    def set_account_locked(self, user_id: int, locked: bool) -> User:
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found")
        user.account_locked = locked
        self.db.flush()
        return user

    def advanced_search(
        self,
        query: str | None = None,
        department: str | None = None,
        role: str | None = None,
        group_id: int | None = None,
        active_only: bool = True,
        locked_only: bool = False,
        limit: int = 50,
    ) -> list[User]:
        q = self.db.query(User).options(
            joinedload(User.ad_groups),
            joinedload(User.manager),
        )
        if active_only:
            q = q.filter(User.is_active.is_(True))
        if locked_only:
            q = q.filter(User.account_locked.is_(True))
        if query:
            pattern = f"%{query}%"
            q = q.filter(
                (User.display_name.ilike(pattern))
                | (User.username.ilike(pattern))
                | (User.email.ilike(pattern))
                | (User.ad_sam_account.ilike(pattern))
                | (User.job_title.ilike(pattern))
            )
        if department:
            q = q.filter(User.department.ilike(f"%{department}%"))
        if role:
            q = q.filter(User.role == role)
        users = q.order_by(User.display_name).limit(limit).all()
        if group_id:
            users = [u for u in users if any(g.id == group_id for g in u.ad_groups)]
        return users

    def get_ad_audit_logs(self, limit: int = 100) -> list:
        from app.models.entities import AuditLog

        return (
            self.db.query(AuditLog)
            .options(joinedload(AuditLog.actor))
            .filter(AuditLog.entity_type.in_(("ad_user", "ad_group", "ad_ou", "ad_directory")))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def ou_user_counts(self) -> dict[int, int]:
        """Count users per OU via group membership."""
        counts: dict[int, int] = {}
        for group in self.list_groups():
            if group.ou_id:
                counts[group.ou_id] = counts.get(group.ou_id, 0) + len(group.members)
        return counts
