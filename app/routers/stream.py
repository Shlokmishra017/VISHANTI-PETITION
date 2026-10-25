from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Header
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.models import Notification, User
from app.schemas import NotificationResponse
from app.auth import get_current_user
from app.sse import notification_event_generator

router = APIRouter(tags=["realtime"])

# sse stream endpoint with last-event-id replay
@router.get("/stream")
async def stream_notifications(
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    db: Session = Depends(get_db)
):
    # extract user from cookie if logged in
    user_id = None
    token = request.cookies.get("access_token")
    if token:
        try:
            import jwt
            from app.config import settings
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("sub")
        except Exception:
            pass

    return EventSourceResponse(
        notification_event_generator(user_id=user_id, last_event_id=last_event_id, db=db)
    )

# list unread or recent notifications for caller
@router.get("/notifications", response_model=List[NotificationResponse])
def get_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notifs = db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).scalars().all()
    return notifs

