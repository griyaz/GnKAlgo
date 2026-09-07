from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.trading import AlertCreateRequest, AlertResponse, AlertUpdateRequest
from app.services.alert_service import alert_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/", response_model=list[AlertResponse])
async def list_alerts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await alert_service.list(db, current_user)


@router.post("/", response_model=AlertResponse, status_code=201)
async def create_alert(data: AlertCreateRequest, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await alert_service.create(db, current_user, data)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(alert_id: UUID, data: AlertUpdateRequest,
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    try:
        return await alert_service.update(db, current_user, alert_id, data.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
