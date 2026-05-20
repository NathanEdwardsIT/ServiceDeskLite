from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session, joinedload

from app.auth.rbac import has_permission
from app.database import get_db
from app.dependencies import require_login, require_permission
from app.models.entities import ADGroup, Device, User
from app.models.enums import AuditAction
from app.services.ad_management_service import ADManagementService
from app.services.audit_service import AuditService
from app.services.device_inventory_service import DeviceInventoryService
from app.services.password_reset_service import PasswordResetService
from app.services.provisioning_service import ProvisioningService

router = APIRouter(tags=["Operations"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/password-resets", response_class=HTMLResponse)
def password_resets_page(
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "password_reset:request", db)
    svc = PasswordResetService(db)
    can_approve = has_permission(current.role, "password_reset:approve")
    last_pw = request.session.pop("last_reset_password", None)
    return templates.TemplateResponse(
        request,
        "password_resets.html",
        {
            "user": current,
            "requests": svc.list_requests(),
            "users": db.query(User).filter(User.is_active.is_(True)).order_by(User.display_name).all(),
            "can_approve": can_approve,
            "last_reset_password": last_pw,
        },
    )


@router.post("/password-resets/create")
def create_password_reset(
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    target_user_id: int = Form(...),
    reason: str = Form(""),
):
    require_permission(current, "password_reset:request", db)
    svc = PasswordResetService(db)
    auto = target_user_id == current.id
    req = svc.create_request(target_user_id, current.id, reason or None, auto_approve=False)
    AuditService(db, request).log(
        AuditAction.PASSWORD_RESET,
        "password_reset",
        req.id,
        current.id,
        summary=f"Password reset requested for user #{target_user_id}",
    )
    db.commit()
    return RedirectResponse("/password-resets", status_code=303)


@router.post("/password-resets/{req_id}/approve")
def approve_reset(req_id: int, request: Request, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "password_reset:approve", db)
    svc = PasswordResetService(db)
    svc.approve(req_id, current.id)
    AuditService(db, request).log(AuditAction.APPROVE, "password_reset", req_id, current.id, summary="Approved reset")
    db.commit()
    return RedirectResponse("/password-resets", status_code=303)


@router.post("/password-resets/{req_id}/complete")
def complete_reset(req_id: int, request: Request, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "password_reset:approve", db)
    svc = PasswordResetService(db)
    req = svc.complete(req_id, current.id)
    temp_pw = getattr(svc, "_last_temp_password", None)
    AuditService(db, request).log(
        AuditAction.PASSWORD_RESET,
        "password_reset",
        req.id,
        current.id,
        summary="Password reset completed",
        severity="warning",
    )
    db.commit()
    if temp_pw:
        request.session["last_reset_password"] = temp_pw
    return RedirectResponse(f"/password-resets?done={req_id}", status_code=303)


@router.post("/password-resets/{req_id}/reject")
def reject_reset(req_id: int, request: Request, current: User = Depends(require_login), db: Session = Depends(get_db)):
    require_permission(current, "password_reset:approve", db)
    svc = PasswordResetService(db)
    svc.reject(req_id, current.id)
    AuditService(db, request).log(AuditAction.REJECT, "password_reset", req_id, current.id)
    db.commit()
    return RedirectResponse("/password-resets", status_code=303)


@router.get("/provisioning", response_class=HTMLResponse)
def provisioning_page(
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "provisioning:manage", db)
    groups = db.query(ADGroup).order_by(ADGroup.name).all()
    managers = db.query(User).filter(User.is_active.is_(True)).order_by(User.display_name).all()
    stock_devices = DeviceInventoryService(db).list_devices(status="in_stock")
    return templates.TemplateResponse(
        request,
        "provisioning.html",
        {
            "user": current,
            "requests": ProvisioningService(db).list_requests(),
            "groups": groups,
            "managers": managers,
            "stock_devices": stock_devices,
        },
    )


@router.post("/provisioning/run")
def run_provisioning(
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    first_name: str = Form(...),
    last_name: str = Form(...),
    department: str = Form(...),
    job_title: str = Form(...),
    manager_id: int | None = Form(None),
    start_date: str = Form(""),
    device_type: str = Form("laptop"),
    assign_existing_device_id: int | None = Form(None),
    group_ids: str = Form(""),
):
    require_permission(current, "provisioning:manage", db)
    gids = [int(x) for x in group_ids.split(",") if x.strip().isdigit()]
    start = None
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    svc = ProvisioningService(db)
    try:
        prov = svc.run_provisioning(
            first_name=first_name,
            last_name=last_name,
            department=department,
            job_title=job_title,
            requested_by_id=current.id,
            manager_id=manager_id,
            start_date=start,
            group_ids=gids,
            device_type=device_type,
            assign_existing_device_id=assign_existing_device_id or None,
        )
        AuditService(db, request).log(
            AuditAction.PROVISION,
            "provisioning",
            prov.id,
            current.id,
            {"email": prov.generated_email, "ticket": prov.onboarding_ticket_id},
            summary=f"Provisioned {prov.first_name} {prov.last_name}",
        )
        db.commit()
        return RedirectResponse(
            f"/provisioning?success={prov.id}&ticket={prov.onboarding_ticket_id}",
            status_code=303,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e


