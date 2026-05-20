import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.rbac import PERMISSION_LABELS, ROLE_LABELS, all_permission_keys, has_permission
from app.database import get_db
from app.dependencies import require_login, require_permission
from app.models.entities import User
from app.models.enums import AuditAction, UserRole
from app.services.ad_management_service import ADManagementService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ad", tags=["Active Directory"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
def ad_console(
    request: Request,
    tab: str = "users",
    selected: int | None = None,
    synced: int | None = None,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "ad:view", db)
    svc = ADManagementService(db)
    can_manage = has_permission(current.role, "ad:manage")
    managers = svc.list_users(active_only=True)
    groups = svc.list_groups()

    script_config = {
        "selectedId": selected,
        "tab": tab,
        "canManage": can_manage,
        "allPermissions": all_permission_keys(),
        "permissionLabels": PERMISSION_LABELS,
        "roleLabels": ROLE_LABELS,
        "roles": [r.value for r in UserRole],
        "groups": [{"id": g.id, "name": g.name} for g in groups],
        "managers": [{"id": m.id, "name": m.display_name} for m in managers],
    }

    perm_matrix = []
    for g in groups[:8]:
        perm_matrix.append(
            {
                "name": g.name,
                "perms": {p.permission for p in g.permissions},
            }
        )

    return templates.TemplateResponse(
        request,
        "ad_console.html",
        {
            "user": current,
            "tab": tab,
            "selected_id": selected,
            "synced_count": synced,
            "can_manage": can_manage,
            "stats": svc.directory_stats(),
            "ou_tree": svc.get_ou_tree(),
            "ous": svc.list_ous(),
            "groups": groups,
            "users": svc.list_users(),
            "managers": managers,
            "all_permissions": all_permission_keys(),
            "permission_labels": PERMISSION_LABELS,
            "role_labels": ROLE_LABELS,
            "roles": [r.value for r in UserRole],
            "script_config_json": json.dumps(script_config),
            "perm_matrix": perm_matrix,
        },
    )


@router.get("/search")
def ad_search(q: str, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:view", db)
    svc = ADManagementService(db)
    return [svc.user_to_dict(u) for u in svc.list_users(query=q)[:30]]


@router.get("/users/{user_id}")
def get_user_api(user_id: int, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:view", db)
    svc = ADManagementService(db)
    u = svc.get_user(user_id)
    if not u:
        raise HTTPException(404)
    return svc.user_to_dict(u)


@router.get("/groups/{group_id}")
def get_group_api(group_id: int, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:view", db)
    svc = ADManagementService(db)
    g = svc.get_group(group_id)
    if not g:
        raise HTTPException(404)
    return svc.group_to_dict(g)


@router.post("/users/create")
def create_user(
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    display_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(""),
    password: str = Form("password"),
    department: str = Form(""),
    job_title: str = Form(""),
    role: str = Form(UserRole.END_USER.value),
    manager_id: int | None = Form(None),
    role_sync_from_groups: bool = Form(False),
    is_active: bool = Form(True),
    group_ids: str = Form(""),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    gids = [int(x) for x in group_ids.split(",") if x.strip().isdigit()]
    try:
        u = svc.create_user(
            display_name=display_name,
            email=email,
            username=username or None,
            password=password,
            department=department or None,
            job_title=job_title or None,
            role=role,
            manager_id=manager_id,
            group_ids=gids,
            role_sync_from_groups=role_sync_from_groups,
            is_active=is_active,
        )
        AuditService(db).log(AuditAction.CREATE, "ad_user", u.id, current.id, {"sam": u.ad_sam_account})
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ad?tab=users&selected={u.id}", status_code=303)


@router.post("/users/{user_id}/update")
def update_user_route(
    user_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    display_name: str = Form(...),
    email: str = Form(...),
    department: str = Form(""),
    job_title: str = Form(""),
    role: str = Form(...),
    manager_id: int | None = Form(None),
    role_sync_from_groups: bool = Form(False),
    is_active: bool = Form(False),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    u = svc.get_user(user_id)
    if not u:
        raise HTTPException(404)
    try:
        svc.update_user(
            u,
            display_name=display_name,
            email=email,
            department=department,
            job_title=job_title,
            role=role,
            manager_id=manager_id,
            role_sync_from_groups=role_sync_from_groups,
            is_active=is_active,
        )
        AuditService(db).log(AuditAction.UPDATE, "ad_user", u.id, current.id)
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ad?tab=users&selected={user_id}", status_code=303)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    new_password: str = Form(...),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.reset_password(user_id, new_password)
    AuditService(db).log(AuditAction.UPDATE, "ad_user", user_id, current.id, {"action": "reset_password"})
    db.commit()
    return RedirectResponse(f"/ad?tab=users&selected={user_id}", status_code=303)


@router.post("/users/{user_id}/groups/add")
def add_user_group(
    user_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    group_id: int = Form(...),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.add_user_to_group(user_id, group_id)
    AuditService(db).log(AuditAction.UPDATE, "ad_user", user_id, current.id, {"add_group": group_id})
    db.commit()
    return RedirectResponse(f"/ad?tab=users&selected={user_id}", status_code=303)


@router.post("/users/{user_id}/groups/remove")
def remove_user_group(
    user_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    group_id: int = Form(...),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.remove_user_from_group(user_id, group_id)
    AuditService(db).log(AuditAction.UPDATE, "ad_user", user_id, current.id, {"remove_group": group_id})
    db.commit()
    return RedirectResponse(f"/ad?tab=users&selected={user_id}", status_code=303)


@router.post("/groups/create")
def create_group_route(
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    ou_id: int | None = Form(None),
    group_type: str = Form("security"),
    mapped_role: str = Form(""),
    role_priority: int = Form(0),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    g = svc.create_group(
        name=name,
        description=description or None,
        ou_id=ou_id,
        group_type=group_type,
        mapped_role=mapped_role or None,
        role_priority=role_priority,
    )
    AuditService(db).log(AuditAction.CREATE, "ad_group", g.id, current.id, {"name": name})
    db.commit()
    return RedirectResponse(f"/ad?tab=groups&selected={g.id}", status_code=303)


@router.post("/groups/{group_id}/update")
def update_group_route(
    group_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    ou_id: int | None = Form(None),
    group_type: str = Form("security"),
    mapped_role: str = Form(""),
    role_priority: int = Form(0),
    clear_mapped_role: bool = Form(False),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    g = svc.get_group(group_id)
    if not g:
        raise HTTPException(404)
    svc.update_group(
        g,
        name=name,
        description=description,
        ou_id=ou_id,
        group_type=group_type,
        mapped_role=mapped_role or None,
        role_priority=role_priority,
        clear_mapped_role=clear_mapped_role,
    )
    AuditService(db).log(AuditAction.UPDATE, "ad_group", g.id, current.id)
    db.commit()
    return RedirectResponse(f"/ad?tab=groups&selected={group_id}", status_code=303)


@router.post("/groups/{group_id}/delete")
def delete_group_route(group_id: int, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.delete_group(group_id)
    AuditService(db).log(AuditAction.DELETE, "ad_group", group_id, current.id)
    db.commit()
    return RedirectResponse("/ad?tab=groups", status_code=303)


@router.post("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: int,
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "ad:manage", db)
    form = await request.form()
    perms = [k.replace("perm_", "") for k in form.keys() if k.startswith("perm_")]
    svc = ADManagementService(db)
    svc.set_group_permissions(group_id, perms)
    AuditService(db).log(AuditAction.UPDATE, "ad_group", group_id, current.id, {"permissions": perms})
    db.commit()
    return RedirectResponse(f"/ad?tab=permissions&selected={group_id}", status_code=303)


@router.post("/groups/{group_id}/members/add")
def add_group_member(
    group_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    user_id: int = Form(...),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.add_user_to_group(user_id, group_id)
    AuditService(db).log(AuditAction.UPDATE, "ad_group", group_id, current.id, {"add_member": user_id})
    db.commit()
    return RedirectResponse(f"/ad?tab=groups&selected={group_id}", status_code=303)


@router.post("/groups/{group_id}/members/remove")
def remove_group_member(
    group_id: int,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    user_id: int = Form(...),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    svc.remove_user_from_group(user_id, group_id)
    AuditService(db).log(AuditAction.UPDATE, "ad_group", group_id, current.id, {"remove_member": user_id})
    db.commit()
    return RedirectResponse(f"/ad?tab=groups&selected={group_id}", status_code=303)


@router.post("/ous/create")
def create_ou_route(
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    name: str = Form(...),
    parent_id: int | None = Form(None),
):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    ou = svc.create_ou(name, parent_id)
    AuditService(db).log(AuditAction.CREATE, "ad_ou", ou.id, current.id, {"name": name})
    db.commit()
    return RedirectResponse("/ad?tab=ous", status_code=303)


@router.post("/ous/{ou_id}/delete")
def delete_ou_route(ou_id: int, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    try:
        svc.delete_ou(ou_id)
        AuditService(db).log(AuditAction.DELETE, "ad_ou", ou_id, current.id)
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse("/ad?tab=ous", status_code=303)


@router.post("/sync-roles")
def sync_all_roles(current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "ad:manage", db)
    svc = ADManagementService(db)
    count = svc.sync_all_roles()
    AuditService(db).log(AuditAction.UPDATE, "ad_directory", None, current.id, {"synced": count})
    db.commit()
    return RedirectResponse(f"/ad?tab=users&synced={count}", status_code=303)
