from __future__ import annotations

from typing import Sequence

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal, get_session
from ..models import LinkSubmission, WebhookStatus
from ..schemas import LinkSubmissionCreate, LinkSubmissionList, LinkSubmissionRead

router = APIRouter(prefix="/links", tags=["links"])


def _post_link_submission_webhook(submission_id: str) -> None:
    settings = get_settings()
    webhook_url = settings.n8n_link_submission_webhook
    if not webhook_url:
        # Webhook disabled; mark as sent to avoid a permanent pending state.
        with SessionLocal() as session:
            submission = session.get(LinkSubmission, submission_id)
            if submission:
                submission.webhook_status = WebhookStatus.SENT
                submission.webhook_attempts = (submission.webhook_attempts or 0) + 1
                session.add(submission)
                session.commit()
        return

    with SessionLocal() as session:
        submission = session.get(LinkSubmission, submission_id)
        if not submission:
            return

        payload = {
            "id": submission.id,
            "url": submission.url,
            "source_url": submission.source_url,
            "created_at": submission.created_at.isoformat(),
            "client_ip": submission.client_ip,
            "user_agent": submission.user_agent,
        }

        submission.webhook_attempts = (submission.webhook_attempts or 0) + 1
        session.add(submission)
        session.commit()

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(str(webhook_url), json=payload)
            resp.raise_for_status()
    except Exception as exc:  # best-effort delivery
        with SessionLocal() as session:
            submission = session.get(LinkSubmission, submission_id)
            if submission:
                submission.webhook_status = WebhookStatus.FAILED
                submission.webhook_last_error = str(exc)
                session.add(submission)
                session.commit()
        return

    with SessionLocal() as session:
        submission = session.get(LinkSubmission, submission_id)
        if submission:
            submission.webhook_status = WebhookStatus.SENT
            submission.webhook_last_error = None
            session.add(submission)
            session.commit()


@router.post("", response_model=LinkSubmissionRead, status_code=status.HTTP_201_CREATED)
def create_link_submission(
    payload: LinkSubmissionCreate,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> LinkSubmission:
    submission = LinkSubmission(
        url=str(payload.url),
        source_url=str(payload.source_url) if payload.source_url is not None else None,
        client_ip=getattr(request.client, "host", None),
        user_agent=request.headers.get("user-agent"),
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    background.add_task(_post_link_submission_webhook, submission.id)
    return submission


@router.get("", response_model=LinkSubmissionList)
def list_link_submissions(
    limit: int = 50,
    session: Session = Depends(get_session),
) -> LinkSubmissionList:
    limit = max(1, min(200, limit))
    stmt = select(LinkSubmission).order_by(LinkSubmission.created_at.desc()).limit(limit)
    submissions: Sequence[LinkSubmission] = session.execute(stmt).scalars().all()
    return LinkSubmissionList(submissions=list(submissions))
