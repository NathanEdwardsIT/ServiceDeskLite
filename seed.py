"""Seed the database with demo AD structure, users, devices, KB, and sample tickets."""

from datetime import datetime, timedelta

from app.auth.passwords import hash_password
from app.database import SessionLocal, init_db
from app.models.entities import (
    ADGroup,
    ADGroupPermission,
    ADOrganizationalUnit,
    AutoResolveScript,
    Device,
    KBArticle,
    Ticket,
    TicketSla,
    User,
)
from app.models.enums import TicketPriority, TicketStatus, UserRole


def seed():
    init_db()
    db = SessionLocal()

    if db.query(User).first():
        print("Database already seeded. Skipping.")
        db.close()
        return

    # AD OUs
    corp = ADOrganizationalUnit(
        name="Corp",
        distinguished_name="OU=Corp,DC=corp,DC=local",
    )
    db.add(corp)
    db.flush()

    it_ou = ADOrganizationalUnit(
        name="IT",
        distinguished_name="OU=IT,OU=Corp,DC=corp,DC=local",
        parent_id=corp.id,
    )
    users_ou = ADOrganizationalUnit(
        name="Users",
        distinguished_name="OU=Users,OU=Corp,DC=corp,DC=local",
        parent_id=corp.id,
    )
    db.add_all([it_ou, users_ou])
    db.flush()

    # AD Groups with role mappings (Azure-style app role assignment via groups)
    groups_data = [
        ("Domain Users", "CN=Domain Users,CN=Users,DC=corp,DC=local", "Default domain group", None, 0),
        ("IT-Helpdesk", "CN=IT-Helpdesk,OU=IT,DC=corp,DC=local", "Help desk technicians", UserRole.TECHNICIAN.value, 10),
        ("IT-Team-Leads", "CN=IT-Team-Leads,OU=IT,DC=corp,DC=local", "Team lead permissions", UserRole.TEAM_LEAD.value, 20),
        ("IT-Admins", "CN=IT-Admins,OU=IT,DC=corp,DC=local", "Full IT administration", UserRole.ADMIN.value, 30),
    ]
    groups = {}
    for name, dn, desc, mapped_role, priority in groups_data:
        g = ADGroup(
            name=name,
            distinguished_name=dn,
            description=desc,
            ou_id=it_ou.id,
            mapped_role=mapped_role,
            role_priority=priority,
        )
        db.add(g)
        groups[name] = g
    db.flush()

    extra_perms = [
        ("IT-Helpdesk", ["ticket:assign", "kb:write"]),
        ("IT-Team-Leads", ["dashboard:performance", "audit:view", "ad:view"]),
        ("IT-Admins", ["ad:manage", "users:manage", "scripts:manage"]),
    ]
    for group_name, perms in extra_perms:
        for perm in perms:
            db.add(ADGroupPermission(group_id=groups[group_name].id, permission=perm))
    db.flush()

    password = hash_password("password")

    def make_user(username, display, email, role, sam, dept, group_names, manager=None):
        u = User(
            username=username,
            display_name=display,
            email=email,
            password_hash=password,
            role=role,
            department=dept,
            ad_sam_account=sam,
            ad_upn=f"{sam}@corp.local",
            manager_id=manager.id if manager else None,
        )
        for gn in group_names:
            u.ad_groups.append(groups[gn])
        db.add(u)
        return u

    admin = make_user("admin", "Alex Admin", "admin@corp.local", UserRole.ADMIN.value, "aadmin", "IT", ["IT-Admins", "Domain Users"])
    lead = make_user("lead1", "Jordan Lead", "lead@corp.local", UserRole.TEAM_LEAD.value, "jlead", "IT", ["IT-Team-Leads", "IT-Helpdesk", "Domain Users"])
    tech1 = make_user("tech1", "Sam Technician", "tech1@corp.local", UserRole.TECHNICIAN.value, "stech", "IT", ["IT-Helpdesk", "Domain Users"], lead)
    tech2 = make_user("tech2", "Riley Tech", "tech2@corp.local", UserRole.TECHNICIAN.value, "rtech", "Infrastructure", ["IT-Helpdesk", "Domain Users"], lead)
    user1 = make_user("user1", "Jamie Smith", "jsmith@corp.local", UserRole.END_USER.value, "jsmith", "Sales", ["Domain Users"])
    user2 = make_user("user2", "Taylor Brown", "tbrown@corp.local", UserRole.END_USER.value, "tbrown", "Marketing", ["Domain Users"])
    db.flush()

    devices = [
        Device(hostname="LAP-JSMITH", asset_tag="AST-1001", device_type="laptop", os="Windows 11", location="NYC", status="deployed", assigned_user_id=user1.id),
        Device(hostname="DSK-TBROWN", asset_tag="AST-1002", device_type="desktop", os="Windows 10", location="Remote", status="deployed", assigned_user_id=user2.id),
        Device(hostname="SRV-FILE01", asset_tag="AST-2001", device_type="server", os="Windows Server 2022", location="DC-1", status="deployed"),
        Device(hostname="LAP-STOCK01", asset_tag="AST-1003", device_type="laptop", os="Windows 11", location="IT Closet", status="in_stock"),
    ]
    db.add_all(devices)
    db.flush()

    kb_articles = [
        KBArticle(
            title="Password Reset Self-Service",
            slug="password-reset-self-service",
            content="Users can reset passwords at https://portal.corp.local/reset. Verify identity via MFA.",
            category="access",
            tags="password, reset, active directory",
            author_id=tech1.id,
            helpful_count=42,
        ),
        KBArticle(
            title="VPN Connection Troubleshooting",
            slug="vpn-connection-troubleshooting",
            content="Restart VPN client, clear credentials, verify gateway vpn.corp.local. Check split tunnel settings.",
            category="network",
            tags="vpn, remote, connectivity",
            author_id=tech2.id,
            helpful_count=38,
        ),
        KBArticle(
            title="Outlook Not Syncing",
            slug="outlook-not-syncing",
            content="Recreate Outlook profile, disable cached mode temporarily, run Office repair.",
            category="email",
            tags="outlook, exchange, email",
            author_id=tech1.id,
            helpful_count=25,
        ),
    ]
    db.add_all(kb_articles)
    db.flush()

    scripts = [
        AutoResolveScript(
            name="Password Reset Guide",
            description="Auto-resolves common password reset requests",
            trigger_keywords="password,reset,forgot,locked out",
            script_path="password_reset_guide.py",
        ),
        AutoResolveScript(
            name="VPN Reconnect",
            description="Runs VPN reconnect playbook",
            trigger_keywords="vpn,disconnect,cannot connect,remote access",
            script_path="vpn_reconnect.py",
        ),
    ]
    db.add_all(scripts)

    now = datetime.utcnow()
    sample_tickets = [
        (user1, devices[0], "Cannot connect to VPN", "VPN keeps disconnecting when I work from home.", TicketPriority.HIGH.value, TicketStatus.IN_PROGRESS.value, tech2),
        (user2, devices[1], "Outlook not syncing", "Emails stuck in outbox since this morning.", TicketPriority.MEDIUM.value, TicketStatus.OPEN.value, tech1),
        (user1, devices[0], "Forgot password", "I forgot my password and need a reset.", TicketPriority.MEDIUM.value, TicketStatus.RESOLVED.value, tech1),
    ]

    for i, (requester, device, title, desc, priority, status, tech) in enumerate(sample_tickets, 1):
        t = Ticket(
            ticket_number=f"INC{100000 + i}",
            title=title,
            description=desc,
            priority=priority,
            status=status,
            category="network" if "VPN" in title else "email" if "Outlook" in title else "access",
            requester_id=requester.id,
            assigned_technician_id=tech.id,
            affected_device_id=device.id,
            created_at=now - timedelta(days=i),
        )
        if status == TicketStatus.RESOLVED.value:
            t.resolved_at = now - timedelta(hours=2)
        db.add(t)
        db.flush()

        sla_targets = {"critical": 60, "high": 240, "medium": 480, "low": 1440}
        target = sla_targets.get(priority, 480)
        sla = TicketSla(
            ticket_id=t.id,
            target_minutes=target,
            started_at=t.created_at,
            due_at=t.created_at + timedelta(minutes=target),
            status="met" if status == TicketStatus.RESOLVED.value else "on_track",
            percent_remaining=0 if status == TicketStatus.RESOLVED.value else 65.0,
        )
        if status == TicketStatus.RESOLVED.value:
            sla.met_at = t.resolved_at
        db.add(sla)

    db.commit()
    print("Database seeded successfully.")
    print("Login with: admin/password, tech1/password, lead1/password, user1/password")
    db.close()


if __name__ == "__main__":
    seed()
