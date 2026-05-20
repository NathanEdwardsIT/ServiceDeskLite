import importlib.util
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import AutoResolveScript, Ticket
from app.models.enums import AuditAction, TicketStatus


class AutoResolveService:
    """Runs registered scripts when ticket text matches trigger keywords."""

    def __init__(self, db: Session):
        self.db = db
        self.scripts_dir = Path(__file__).resolve().parent.parent / "scripts" / "auto_resolve"

    def _match_script(self, script: AutoResolveScript, title: str, description: str) -> bool:
        keywords = [k.strip().lower() for k in script.trigger_keywords.split(",") if k.strip()]
        text = f"{title} {description}".lower()
        return any(kw in text for kw in keywords)

    def _run_script_module(self, script_path: str, ticket: Ticket) -> dict:
        full_path = self.scripts_dir / script_path
        if not full_path.exists():
            return {"success": False, "message": f"Script not found: {script_path}"}

        spec = importlib.util.spec_from_file_location(f"auto_resolve_{script_path}", full_path)
        if not spec or not spec.loader:
            return {"success": False, "message": "Failed to load script module"}

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            return {"success": False, "message": "Script missing run(ticket) function"}

        return module.run(ticket)

    def try_auto_resolve(self, ticket: Ticket) -> dict | None:
        scripts = (
            self.db.query(AutoResolveScript)
            .filter(AutoResolveScript.is_enabled.is_(True))
            .all()
        )
        for script in scripts:
            if not self._match_script(script, ticket.title, ticket.description):
                continue

            script.run_count += 1
            result = self._run_script_module(script.script_path, ticket)

            if result.get("success"):
                script.success_count += 1
                ticket.status = TicketStatus.RESOLVED.value
                from datetime import datetime

                ticket.resolved_at = datetime.utcnow()
                self.db.flush()

            return {
                "script": script.name,
                "result": result,
            }
        return None
