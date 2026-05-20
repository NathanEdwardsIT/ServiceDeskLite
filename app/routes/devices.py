from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from app.auth.rbac import has_permission
from app.database import get_db
from app.dependencies import require_login, require_permission
from app.models.entities import User
from app.models.enums import AuditAction
from app.services.audit_service import AuditService
from app.services.device_inventory_service import DeviceInventoryService

router = APIRouter(prefix="/devices", tags=["Devices"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
def device_inventory(
    request: Request,
    q: str = "",
    status: str = "",
    device_type: str = "",
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "devices:view", db)
    svc = DeviceInventoryService(db)
    devices = svc.list_devices(
        status=status or None,
        device_type=device_type or None,
        query=q or None,
    )
    return templates.TemplateResponse(
        request,
        "devices.html",
        {
            "user": current,
            "devices": devices,
            "stats": svc.inventory_stats(),
            "query": q,
            "filter_status": status,
            "filter_type": device_type,
            "can_manage": has_permission(current.role, "devices:manage"),
        },
    )


@router.get("/{device_id}", response_class=HTMLResponse)
def device_detail_page(
    device_id: int,
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "devices:view", db)
    svc = DeviceInventoryService(db)
    device = svc.get_device(device_id)
    if not device:
        raise HTTPException(404)
    tickets = svc.get_ticket_history(device_id)
    audit = AuditService(db, request).get_for_entity("device", device_id)
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.display_name).all()
    return templates.TemplateResponse(
        request,
        "device_detail.html",
        {
            "user": current,
            "device": device,
            "tickets": tickets,
            "audit_logs": audit[:20],
            "users": users,
            "can_manage": has_permission(current.role, "devices:manage"),
        },
    )


@router.post("/create")
def create_device(
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    device_type: str = Form(...),
    hostname: str = Form(""),
    manufacturer: str = Form(""),
    model: str = Form(""),
    serial_number: str = Form(""),
    os: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
):
    require_permission(current, "devices:manage", db)
    svc = DeviceInventoryService(db)
    d = svc.create_device(
        device_type=device_type,
        hostname=hostname or None,
        manufacturer=manufacturer or None,
        model=model or None,
        serial_number=serial_number or None,
        os=os or None,
        location=location or None,
        notes=notes or None,
    )
    AuditService(db, request).log(
        AuditAction.CREATE,
        "device",
        d.id,
        current.id,
        {"hostname": d.hostname},
        summary=f"Added device {d.hostname}",
    )
    db.commit()
    return RedirectResponse(f"/devices/{d.id}", status_code=303)


@router.post("/{device_id}/update")
def update_device(
    device_id: int,
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    manufacturer: str = Form(""),
    model: str = Form(""),
    os: str = Form(""),
    location: str = Form(""),
    status: str = Form(""),
    notes: str = Form(""),
):
    require_permission(current, "devices:manage", db)
    svc = DeviceInventoryService(db)
    device = svc.get_device(device_id)
    if not device:
        raise HTTPException(404)
    svc.update_device(
        device,
        manufacturer=manufacturer or None,
        model=model or None,
        os=os or None,
        location=location or None,
        status=status or None,
        notes=notes or None,
    )
    AuditService(db, request).log(
        AuditAction.UPDATE, "device", device_id, current.id, summary=f"Updated {device.hostname}"
    )
    db.commit()
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@router.post("/{device_id}/assign")
def assign_device(
    device_id: int,
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
    user_id: int | None = Form(None),
):
    require_permission(current, "devices:manage", db)
    svc = DeviceInventoryService(db)
    device = svc.assign_to_user(device_id, user_id if user_id else None)
    AuditService(db, request).log(
        AuditAction.DEVICE_ASSIGN,
        "device",
        device_id,
        current.id,
        {"user_id": user_id},
        summary=f"Device {device.hostname} assignment changed",
        severity="info",
    )
    db.commit()
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@router.post("/{device_id}/retire")
def retire_device(
    device_id: int,
    request: Request,
    current: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    require_permission(current, "devices:manage", db)
    svc = DeviceInventoryService(db)
    device = svc.retire_device(device_id)
    AuditService(db, request).log(
        AuditAction.UPDATE,
        "device",
        device_id,
        current.id,
        summary=f"Retired device {device.hostname}",
        severity="warning",
    )
    db.commit()
    return RedirectResponse("/devices", status_code=303)
