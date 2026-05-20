from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth.ad_simulation import ActiveDirectorySimulator
from app.auth.rbac import has_permission
from app.config import settings
from app.database import get_db, init_db
from app.dependencies import require_login
from app.models.entities import Device, KBArticle, Ticket, User
from app.routes import ad_router
from app.models.enums import AuditAction, TicketStatus
from app.services.audit_service import AuditService
from app.services.device_service import DeviceService
from app.services.documentation_service import DocumentationService
from app.services.kb_service import KnowledgeBaseService
from app.services.performance_service import PerformanceService
from app.services.sla_service import SlaService
from app.services.ticket_service import TicketService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

PUBLIC_PATHS = {"/login", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


@app.middleware("http")
async def require_session_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLIC_PATHS or (path == "/login" and request.method == "POST"):
        return await call_next(request)
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


# Must be added AFTER the auth middleware above so SessionMiddleware runs first
# (Starlette runs last-added middleware first on incoming requests).
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.include_router(ad_router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ad = ActiveDirectorySimulator(db)
    user = ad.authenticate(username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid credentials (AD simulation)"},
            status_code=401,
        )
    synced_role = ad.sync_role_from_groups(user)
    if synced_role != user.role:
        user.role = synced_role
        db.commit()
    request.session["user_id"] = user.id
    AuditService(db).log(AuditAction.LOGIN, "user", user.id, user.id)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        AuditService(db).log(AuditAction.LOGOUT, "user", user_id, user_id)
        db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    perf = PerformanceService(db)
    stats = perf.queue_stats()
    tech_stats = perf.technician_dashboard() if has_permission(user.role, "dashboard:performance") else []
    recent = TicketService(db).list_tickets()[:10]
    for t in recent:
        if t.sla:
            SlaService(db).refresh(t)
    db.commit()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "stats": stats, "tech_stats": tech_stats, "recent": recent},
    )


@app.get("/tickets", response_class=HTMLResponse)
def tickets_list(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    svc = TicketService(db)
    if has_permission(user.role, "ticket:view_all"):
        tickets = svc.list_tickets()
    else:
        tickets = [t for t in svc.list_tickets() if t.requester_id == user.id or t.assigned_technician_id == user.id]
    sla_svc = SlaService(db)
    timers = {}
    for t in tickets:
        if t.sla:
            sla_svc.refresh(t)
            timers[t.id] = sla_svc.format_timer_display(t.sla)
    db.commit()
    return templates.TemplateResponse(
        request,
        "tickets.html",
        {"user": user, "tickets": tickets, "timers": timers},
    )


@app.get("/tickets/new", response_class=HTMLResponse)
def new_ticket_form(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    devices = db.query(Device).filter(Device.is_active.is_(True)).all()
    return templates.TemplateResponse(
        request,
        "ticket_new.html",
        {"user": user, "devices": devices},
    )


@app.post("/tickets/new")
def create_ticket(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
    title: str = Form(...),
    description: str = Form(...),
    priority: str = Form("medium"),
    affected_device_id: int | None = Form(None),
    category: str | None = Form(None),
):
    device_id = affected_device_id if affected_device_id else None
    result = TicketService(db).create_ticket(
        title=title,
        description=description,
        priority=priority,
        requester_id=user.id,
        affected_device_id=device_id,
        category=category,
        actor_id=user.id,
    )
    ticket = result["ticket"]
    return RedirectResponse(f"/tickets/{ticket.id}", status_code=303)


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(
    ticket_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    ticket = TicketService(db).get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    from app.auth.rbac import can_view_ticket

    if not can_view_ticket(user.role, user.id, ticket.requester_id, ticket.assigned_technician_id):
        raise HTTPException(403, "Access denied")

    sla_display = None
    if ticket.sla:
        sla_display = SlaService(db).format_timer_display(SlaService(db).refresh(ticket))

    device_history = []
    if ticket.affected_device_id:
        device_history = DeviceService(db).get_history(ticket.affected_device_id)

    kb_suggestions = KnowledgeBaseService(db).suggest_for_ticket(ticket.title, ticket.description)
    dupes = TicketService(db).duplicates.find_duplicates(
        ticket.title, ticket.description, ticket.affected_device_id, exclude_ticket_id=ticket.id
    )
    technicians = TicketService(db).assignment.get_available_technicians()
    db.commit()

    return templates.TemplateResponse(
        request,
        "ticket_detail.html",
        {
            "user": user,
            "ticket": ticket,
            "sla_display": sla_display,
            "device_history": device_history,
            "kb_suggestions": kb_suggestions,
            "duplicates": dupes,
            "technicians": technicians,
            "statuses": [s.value for s in TicketStatus],
        },
    )


@app.post("/tickets/{ticket_id}/status")
def update_status(
    ticket_id: int,
    new_status: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not has_permission(user.role, "ticket:update"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    TicketService(db).update_status(ticket, new_status, user.id, note or None)
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: int,
    technician_id: int = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not has_permission(user.role, "ticket:assign"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    tech = TicketService(db).assignment.manual_assign(ticket, technician_id)
    if tech:
        AuditService(db).log(AuditAction.ASSIGN, "ticket", ticket.id, user.id, {"technician_id": tech.id})
        db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/work-note")
def add_work_note(
    ticket_id: int,
    content: str = Form(...),
    note_type: str = Form("investigation"),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not has_permission(user.role, "ticket:work_note"):
        raise HTTPException(403)
    DocumentationService(db).add_work_note(ticket_id, user.id, content, note_type)
    AuditService(db).log(AuditAction.COMMENT, "ticket", ticket_id, user.id)
    db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: int,
    root_cause: str = Form(...),
    resolution_steps: str = Form(...),
    prevention_notes: str = Form(""),
    verification_steps: str = Form(""),
    time_spent_minutes: int = Form(0),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    if not has_permission(user.role, "ticket:resolve"):
        raise HTTPException(403)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    DocumentationService(db).create_resolution_doc(
        ticket,
        user.id,
        root_cause,
        resolution_steps,
        prevention_notes or None,
        verification_steps=verification_steps or None,
        time_spent_minutes=time_spent_minutes or None,
    )
    TicketService(db).update_status(ticket, TicketStatus.RESOLVED.value, user.id, "Resolved with documentation")
    AuditService(db).log(AuditAction.RESOLVE, "ticket", ticket.id, user.id)
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/link-duplicate")
def link_duplicate(
    ticket_id: int,
    master_id: int = Form(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    master = TicketService(db).duplicates.link_duplicate(ticket, master_id)
    if master:
        AuditService(db).log(
            AuditAction.DUPLICATE_LINK,
            "ticket",
            ticket.id,
            user.id,
            {"master_id": master.id},
        )
        db.commit()
    return RedirectResponse(f"/tickets/{master_id}", status_code=303)


@app.get("/kb", response_class=HTMLResponse)
def kb_list(request: Request, q: str = "", user: User = Depends(require_login), db: Session = Depends(get_db)):
    svc = KnowledgeBaseService(db)
    articles = svc.search(q) if q else db.query(KBArticle).filter(KBArticle.is_published.is_(True)).all()
    return templates.TemplateResponse(
        request,
        "kb.html",
        {"user": user, "articles": articles, "query": q},
    )


@app.get("/devices/{device_id}", response_class=HTMLResponse)
def device_detail(
    device_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    summary = DeviceService(db).device_summary(device_id)
    if not summary:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "device.html",
        {"user": user, **summary},
    )


@app.get("/audit", response_class=HTMLResponse)
def audit_log(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    if not has_permission(user.role, "audit:view"):
        raise HTTPException(403)
    logs = AuditService(db).get_recent(100)
    return templates.TemplateResponse(
        request,
        "audit.html",
        {"user": user, "logs": logs},
    )
