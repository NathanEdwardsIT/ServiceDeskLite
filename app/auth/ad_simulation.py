"""Active Directory simulation: OUs, groups, UPN/SAM accounts, and LDAP-style lookups."""

from sqlalchemy.orm import Session, joinedload

from app.models.entities import ADGroup, ADOrganizationalUnit, User


class ActiveDirectorySimulator:
    def __init__(self, db: Session):
        self.db = db

    def search_users(self, query: str, limit: int = 20, include_inactive: bool = False) -> list[User]:
        pattern = f"%{query}%"
        q = self.db.query(User).options(joinedload(User.ad_groups))
        if not include_inactive:
            q = q.filter(User.is_active.is_(True))
        return (
            q.filter(
                (User.display_name.ilike(pattern))
                | (User.username.ilike(pattern))
                | (User.email.ilike(pattern))
                | (User.ad_sam_account.ilike(pattern))
                | (User.ad_upn.ilike(pattern)),
            )
            .limit(limit)
            .all()
        )

    def get_user_by_sam(self, sam_account: str) -> User | None:
        return self.db.query(User).filter(User.ad_sam_account == sam_account).first()

    def get_user_by_upn(self, upn: str) -> User | None:
        return self.db.query(User).filter(User.ad_upn == upn).first()

    def get_group_members(self, group_name: str) -> list[User]:
        group = self.db.query(ADGroup).filter(ADGroup.name == group_name).first()
        if not group:
            return []
        return list(group.members)

    def user_in_group(self, user: User, group_name: str) -> bool:
        return any(g.name == group_name for g in user.ad_groups)

    def get_ou_tree(self) -> list[dict]:
        from app.services.ad_management_service import ADManagementService

        return ADManagementService(self.db).get_ou_tree()

    def authenticate(self, username: str, password: str) -> User | None:
        user = (
            self.db.query(User)
            .options(joinedload(User.ad_groups))
            .filter(
                (User.username == username)
                | (User.ad_sam_account == username)
                | (User.ad_upn == username),
                User.is_active.is_(True),
            )
            .first()
        )
        if not user:
            return None
        from app.auth.passwords import verify_password

        if not verify_password(password, user.password_hash):
            return None
        return user

    def sync_role_from_groups(self, user: User) -> str:
        if user.role_sync_from_groups:
            from app.services.ad_management_service import ADManagementService

            return ADManagementService(self.db).sync_user_role(user)
        return user.role
