from __future__ import annotations

import httpx
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..database import SessionLocal
from ..models import RunImageApproval, WebhookStatus


def enqueue_run_image_approval_webhook(approval_id: str) -> None:
    settings = get_settings()
    if not settings.n8n_approval_webhook:
        return

    with SessionLocal() as session:
        approval = session.get(
            RunImageApproval,
            approval_id,
            options=(selectinload(RunImageApproval.run_image),),
        )
        if not approval:
            return

        approval.webhook_attempts += 1
        payload = {
            "approval_id": approval.id,
            "run_id": approval.run_image.run_id,
            "image_id": approval.run_image_id,
            "asset_uri": approval.run_image.asset_uri,
            "approved_by": approval.approved_by,
            "approved_at": approval.approved_at.isoformat(),
            "notes": approval.notes,
        }

        try:
            response = httpx.post(
                settings.n8n_approval_webhook,
                json=payload,
                timeout=settings.request_timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network errors only
            approval.webhook_status = WebhookStatus.FAILED
            approval.webhook_last_error = str(exc)
        else:
            approval.webhook_status = WebhookStatus.SENT
            approval.webhook_last_error = None

        session.add(approval)
        session.commit()
