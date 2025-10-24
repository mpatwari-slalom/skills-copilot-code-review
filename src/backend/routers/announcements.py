"""
Announcements management endpoints.

Public: GET /announcements - returns active announcements (based on start/expiration)
Management (requires teacher_username query param referring to a valid teacher):
  GET /announcements/manage
  POST /announcements
  PUT /announcements/{id}
  DELETE /announcements/{id}

Announcements documents shape:
  {
    "_id": "<string id>",
    "message": "...",
    "start_date": "YYYY-MM-DD" or None,
    "expiration_date": "YYYY-MM-DD"
  }
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime
from bson.objectid import ObjectId
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection
from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _ensure_teacher(username: str):
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements which are currently active (start_date <= today <= expiration_date)

    If start_date is missing, announcement is considered active immediately until expiration.
    Dates are stored as YYYY-MM-DD strings.
    """
    today = datetime.utcnow().date()
    results = []
    for ann in announcements_collection.find({}):
        try:
            exp = datetime.strptime(ann.get("expiration_date"), "%Y-%m-%d").date()
        except Exception:
            # Skip malformed entries
            continue

        start_raw = ann.get("start_date")
        if start_raw:
            try:
                start = datetime.strptime(start_raw, "%Y-%m-%d").date()
            except Exception:
                start = None
        else:
            start = None

        # Announcements are visible through their expiration date (inclusive)
        if (start is None or start <= today) and today <= exp:
            results.append({
                "id": str(ann.get("_id")),
                "message": ann.get("message"),
                "start_date": ann.get("start_date"),
                "expiration_date": ann.get("expiration_date"),
            })

    # sort by expiration_date ascending, missing expiration_date goes last
    results.sort(key=lambda r: (r.get("expiration_date") is None, r.get("expiration_date") or ""))
    return results


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: str = None):
    _ensure_teacher(teacher_username)
    results = []
    for ann in announcements_collection.find({}):
        results.append({
            "id": str(ann.get("_id")),
            "message": ann.get("message"),
            "start_date": ann.get("start_date"),
            "expiration_date": ann.get("expiration_date"),
        })
    # newest first by insertion order would be fine; reverse list to show newest top
    results.reverse()
    return results


class AnnouncementPayload(BaseModel):
    message: str
    expiration_date: str
    start_date: Optional[str] = None

@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: str = None):
    _ensure_teacher(teacher_username)

    message = payload.message
    expiration_date = payload.expiration_date
    start_date = payload.start_date

    try:
        exp = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="expiration_date must be YYYY-MM-DD")

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD if provided")
        if start > exp:
            raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    # persist
    doc = {
        "message": message,
        "start_date": start_date,
        "expiration_date": expiration_date,
    }
    result = announcements_collection.insert_one(doc)
class AnnouncementUpdate(BaseModel):
    message: Optional[str] = None
    start_date: Optional[str] = None
    expiration_date: Optional[str] = None

@router.put("/{ann_id}", response_model=Dict[str, Any])
def update_announcement(ann_id: str, payload: AnnouncementUpdate, teacher_username: str = None):
    _ensure_teacher(teacher_username)

    try:
        oid = ObjectId(ann_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    ann = announcements_collection.find_one({"_id": oid})
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates = {}
    if payload.message is not None:
        updates["message"] = payload.message
    if payload.start_date is not None:
        updates["start_date"] = payload.start_date
    if "expiration_date" in updates:
        exp_raw = updates.get("expiration_date")
        if exp_raw is not None:
            try:
                exp = datetime.strptime(exp_raw, "%Y-%m-%d").date()
            except Exception:
                raise HTTPException(status_code=400, detail="expiration_date must be YYYY-MM-DD")
            start_raw = updates.get("start_date", ann.get("start_date"))
            if start_raw:
                try:
                    start = datetime.strptime(start_raw, "%Y-%m-%d").date()
                except Exception:
                    raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD if provided")
                if start > exp:
                    raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")
                raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD if provided")
            if start > exp:
                raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    if updates:
        announcements_collection.update_one({"_id": oid}, {"$set": updates})

    updated = announcements_collection.find_one({"_id": oid})
    return {
        "id": str(updated.get("_id")),
        "message": updated.get("message"),
        "start_date": updated.get("start_date"),
        "expiration_date": updated.get("expiration_date")
    }

    updated = announcements_collection.find_one({"_id": oid})
    return {"id": str(updated.get("_id")), "message": updated.get("message"), "start_date": updated.get("start_date"), "expiration_date": updated.get("expiration_date")}


@router.delete("/{ann_id}")
def delete_announcement(ann_id: str, teacher_username: str = None):
    _ensure_teacher(teacher_username)
    try:
        oid = ObjectId(ann_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    res = announcements_collection.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
