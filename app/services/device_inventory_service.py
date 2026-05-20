from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.entities import Device, Ticket
from app.models.enums import AuditAction, DeviceStatus


class DeviceInventoryService:
    def __init__(self, db: Session):
        self.db = db

    def list_devices(
        self,
        status: str | None = None,
        device_type: str | None = None,
        query: str | None = None,
        include_retired: bool = False,
    ) -> list[Device]:
        q = self.db.query(Device).options(joinedload(Device.assigned_user))
        if not include_retired:
            q = q.filter(Device.is_active.is_(True))
        if status:
            q = q.filter(Device.status == status)
        if device_type:
            q = q.filter(Device.device_type == device_type)
        if query:
            pattern = f"%{query}%"
            q = q.filter(
                (Device.hostname.ilike(pattern))
                | (Device.asset_tag.ilike(pattern))
                | (Device.serial_number.ilike(pattern))
            )
        return q.order_by(Device.hostname).all()

    def get_device(self, device_id: int) -> Device | None:
        return (
            self.db.query(Device)
            .options(joinedload(Device.assigned_user))
            .filter(Device.id == device_id)
            .first()
        )

    def _next_asset_tag(self) -> str:
        count = self.db.query(Device).count()
        return f"AST-{2000 + count + 1}"

    def _next_hostname(self, device_type: str) -> str:
        prefix = {"laptop": "LAP", "desktop": "DSK", "server": "SRV", "mobile": "MOB"}.get(
            device_type, "DEV"
        )
        count = self.db.query(Device).filter(Device.hostname.like(f"{prefix}-%")).count()
        return f"{prefix}-{count + 1:04d}"

    def create_device(
        self,
        device_type: str,
        hostname: str | None = None,
        asset_tag: str | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        serial_number: str | None = None,
        os: str | None = None,
        location: str | None = None,
        status: str = DeviceStatus.IN_STOCK.value,
        notes: str | None = None,
    ) -> Device:
        device = Device(
            hostname=hostname or self._next_hostname(device_type),
            asset_tag=asset_tag or self._next_asset_tag(),
            device_type=device_type,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial_number,
            os=os,
            location=location,
            status=status,
            notes=notes,
        )
        self.db.add(device)
        self.db.flush()
        return device

    def update_device(self, device: Device, **fields) -> Device:
        for key, value in fields.items():
            if hasattr(device, key) and value is not None:
                setattr(device, key, value)
        device.updated_at = datetime.utcnow()
        self.db.flush()
        return device

    def assign_to_user(self, device_id: int, user_id: int | None) -> Device:
        device = self.get_device(device_id)
        if not device:
            raise ValueError("Device not found")
        device.assigned_user_id = user_id
        device.status = DeviceStatus.DEPLOYED.value if user_id else DeviceStatus.IN_STOCK.value
        device.updated_at = datetime.utcnow()
        self.db.flush()
        return device

    def retire_device(self, device_id: int) -> Device:
        device = self.get_device(device_id)
        if not device:
            raise ValueError("Device not found")
        device.is_active = False
        device.status = DeviceStatus.RETIRED.value
        device.assigned_user_id = None
        device.updated_at = datetime.utcnow()
        self.db.flush()
        return device

    def inventory_stats(self) -> dict:
        devices = self.db.query(Device).filter(Device.is_active.is_(True)).all()
        by_status = {}
        by_type = {}
        for d in devices:
            by_status[d.status] = by_status.get(d.status, 0) + 1
            by_type[d.device_type] = by_type.get(d.device_type, 0) + 1
        return {
            "total": len(devices),
            "by_status": by_status,
            "by_type": by_type,
            "unassigned": sum(1 for d in devices if not d.assigned_user_id and d.status == "in_stock"),
        }

    def get_ticket_history(self, device_id: int, limit: int = 25) -> list[Ticket]:
        return (
            self.db.query(Ticket)
            .filter(Ticket.affected_device_id == device_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .all()
        )
