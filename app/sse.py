import asyncio
import json
from typing import AsyncGenerator, Dict, Set, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Notification

# thread-safe listener queues for active sse clients
_active_listeners: Set[asyncio.Queue] = set()

# register new sse client listener queue
def register_listener() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _active_listeners.add(q)
    return q

# unregister sse client listener queue
def unregister_listener(q: asyncio.Queue):
    _active_listeners.discard(q)

# broadcast event payload to all connected active clients
def broadcast_event(event_id: str, case_id: str, kind: str):
    payload = {
        "id": event_id,
        "case_id": case_id,
        "kind": kind
    }
    for q in list(_active_listeners):
        try:
            q.put_nowait(payload)
        except Exception:
            pass

# generate sse event stream with last-event-id replay support
async def notification_event_generator(
    user_id: Optional[str],
    last_event_id: Optional[str],
    db: Session
) -> AsyncGenerator[Dict[str, str], None]:
    q = register_listener()
    try:
        # replay missed notifications if last-event-id is provided
        if last_event_id:
            query = select(Notification).order_by(Notification.created_at.asc())
            if user_id:
                query = query.where(Notification.user_id == user_id)
            
            # find anchor notification
            anchor = db.execute(select(Notification).where(Notification.id == last_event_id)).scalar_one_or_none()
            if anchor:
                query = query.where(Notification.created_at > anchor.created_at)
                missed = db.execute(query).scalars().all()
                for notif in missed:
                    yield {
                        "id": str(notif.id),
                        "event": "notification",
                        "data": json.dumps({"id": str(notif.id), "case_id": str(notif.case_id), "kind": notif.kind})
                    }

        # stream live real-time events
        while True:
            try:
                # wait for new event with heartbeat timeout
                data = await asyncio.wait_for(q.get(), timeout=15.0)
                yield {
                    "id": str(data["id"]),
                    "event": "notification",
                    "data": json.dumps(data)
                }
            except asyncio.TimeoutError:
                # send sse comment heartbeat to keep connection alive
                yield {"comment": "heartbeat"}

    finally:
        unregister_listener(q)

