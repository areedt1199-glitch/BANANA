from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.entities import Alert
from app.schemas.domain import AlertResponse

router = APIRouter(prefix="/alerts", tags=["Alerts & Warnings"])

@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    unresolved_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    query = select(Alert).order_by(Alert.created_at.desc())
    if unresolved_only:
        query = query.where(Alert.is_resolved == False)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/resolve/{alert_id}")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "success", "message": f"Alert '{alert.title}' resolved"}
