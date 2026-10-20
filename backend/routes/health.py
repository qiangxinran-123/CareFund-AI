from datetime import datetime, timezone

from fastapi import APIRouter

from ..models import HealthResponse


router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse, operation_id="get_health")
async def get_health() -> HealthResponse:
    return HealthResponse(time=datetime.now(timezone.utc))

