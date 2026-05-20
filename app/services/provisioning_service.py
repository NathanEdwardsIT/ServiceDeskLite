import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import ProvisioningRequest
from app.models.enums import (
    AuditAction,
    ProvisioningStatus,
    TicketPriority,
    TicketType,
    TimelineEventType,
)
from app.services.ad_management_service import ADManagementService
from app.services.device_inventory_service import DeviceInventoryService
from app.services.ticket_service import TicketService
from app.services.timeline_service import TimelineService


class ProvisioningService:
    DOMAIN = "corp.local"

    def __init__(self, db: Session):
        self.db = db

    def list_requests(self, limit: int = 50) -> list[ProvisioningRequest]:
        return (
            self.db.query(ProvisioningRequest)
            .order_by(ProvisioningRequest.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_request(self, prov_id: int) -> ProvisioningRequest | None:
        return self.db.query(ProvisioningRequest).filter(ProvisioningRequest.id == prov_id).first()

    def _generate_username(self, first: str, last: str) -> str:
        base = f"{first.lower()}.{last.lower()}".replace(" ", "")
        ad = ADManagementService(self.db)
        candidate = ad._unique_sam(base)
        return candidate

    def _generate_email(self, username: str) -> str:
        return f"{username}@{self.DOMAIN}"

    def run_provisioning(
        self,
        first_name: str,
        last_name: str,
        department: str,
        job_title: str,
        requested_by_id: int,
        manager_id: int | None = None,
        start_date: datetime | None = None,
        group_ids: list[int] | None = None,
        device_type: str = "laptop",
        assign_existing_device_id: int | None = None,
        default_password: str = "Welcome2024!",
    ) -> ProvisioningRequest:
        steps: list[dict] = []
        prov = ProvisioningRequest(
            first_name=first_name,
            last_name=last_name,
            department=department,
            job_title=job_title,
            manager_id=manager_id,
            start_date=start_date,
            status=ProvisioningStatus.IN_PROGRESS.value,
            requested_by_id=requested_by_id,
            group_ids_json=json.dumps(group_ids or []),
            steps_json="[]",
        )
        self.db.add(prov)
        self.db.flush()

        try:
            username = self._generate_username(first_name, last_name)
            email = self._generate_email(username)
            display_name = f"{first_name} {last_name}"

            prov.generated_username = username
            prov.generated_email = email
            steps.append({"step": "generate_identity", "status": "ok", "username": username, "email": email})

            ad = ADManagementService(self.db)
            user = ad.create_user(
                display_name=display_name,
                email=email,
                username=username,
                password=default_password,
                department=department,
                job_title=job_title,
                role="end_user",
                manager_id=manager_id,
                group_ids=group_ids or [],
                role_sync_from_groups=True,
            )
            prov.created_user_id = user.id
            steps.append({"step": "create_ad_user", "status": "ok", "user_id": user.id})

            if group_ids:
                steps.append({"step": "assign_groups", "status": "ok", "group_ids": group_ids})

            inv = DeviceInventoryService(self.db)
            if assign_existing_device_id:
                device = inv.assign_to_user(assign_existing_device_id, user.id)
            else:
                device = inv.create_device(
                    device_type=device_type,
                    status="deployed",
                )
                device = inv.assign_to_user(device.id, user.id)
            prov.assigned_device_id = device.id
            steps.append({"step": "assign_device", "status": "ok", "device_id": device.id, "hostname": device.hostname})

            ticket_svc = TicketService(self.db)
            result = ticket_svc.create_ticket(
                title=f"Employee onboarding: {display_name}",
                description=(
                    f"Automated onboarding workflow completed.\n\n"
                    f"**New hire:** {display_name}\n"
                    f"**Email:** {email}\n"
                    f"**Username:** {username}\n"
                    f"**Department:** {department}\n"
                    f"**Job title:** {job_title}\n"
                    f"**Device:** {device.hostname} ({device.asset_tag})\n"
                    f"**Start date:** {start_date.strftime('%Y-%m-%d') if start_date else 'TBD'}\n\n"
                    f"Tasks: deliver hardware, verify MFA enrollment, schedule orientation."
                ),
                priority=TicketPriority.MEDIUM.value,
                requester_id=requested_by_id,
                affected_device_id=device.id,
                category="onboarding",
                auto_assign=True,
                actor_id=requested_by_id,
            )
            ticket = result["ticket"]
            ticket.ticket_type = TicketType.ONBOARDING.value
            ticket.requester_id = user.id
            prov.onboarding_ticket_id = ticket.id
            steps.append({"step": "create_onboarding_ticket", "status": "ok", "ticket_id": ticket.id})

            TimelineService(self.db).add_event(
                ticket.id,
                TimelineEventType.CREATED,
                "Provisioning workflow initiated",
                f"New employee {display_name} provisioned via workflow #{prov.id}",
                requested_by_id,
                {"provisioning_id": prov.id},
            )

            prov.status = ProvisioningStatus.COMPLETED.value
            prov.completed_at = datetime.utcnow()
            prov.steps_json = json.dumps(steps)
            self.db.flush()
            return prov

        except Exception as e:
            prov.status = ProvisioningStatus.FAILED.value
            prov.error_message = str(e)
            steps.append({"step": "error", "status": "failed", "message": str(e)})
            prov.steps_json = json.dumps(steps)
            self.db.flush()
            raise
