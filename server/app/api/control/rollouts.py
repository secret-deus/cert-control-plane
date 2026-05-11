"""Control API – Rollout orchestration endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import write_audit
from app.database import get_db
from app.models import Rollout, RolloutStatus
from app.orchestrator.rollout import (
    create_rollout,
    pause_rollout,
    resume_rollout,
    rollback_rollout,
)
from app.schemas import (
    PaginatedResponse,
    RolloutCreate,
    RolloutDetail,
    RolloutRead,
)

from app.api.control._helpers import _actor, _ip

router = APIRouter()


@router.post(
    "/rollouts",
    response_model=RolloutRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / rollouts"],
    summary="创建 Rollout",
)
async def create_rollout_endpoint(
    body: RolloutCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await create_rollout(
        db,
        name=body.name,
        description=body.description,
        batch_size=body.batch_size,
        target_filter=body.target_filter,
        created_by=_actor(request),
    )
    await write_audit(
        db,
        action="rollout_created",
        entity_type="rollout",
        entity_id=rollout.id,
        actor=_actor(request),
        details={"name": rollout.name, "total_batches": rollout.total_batches},
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.get(
    "/rollouts",
    response_model=PaginatedResponse[RolloutRead],
    tags=["control / rollouts"],
    summary="Rollout 列表",
)
async def list_rollouts(
    status_filter: RolloutStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = select(Rollout)
    if status_filter:
        base = base.where(Rollout.status == status_filter)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    result = await db.execute(
        base.offset(skip).limit(limit).order_by(Rollout.created_at.desc())
    )
    return PaginatedResponse(
        items=list(result.scalars().all()), total=total, skip=skip, limit=limit
    )


@router.get(
    "/rollouts/{rollout_id}",
    response_model=RolloutDetail,
    tags=["control / rollouts"],
    summary="Rollout 详情",
    responses={404: {"description": "Rollout 不存在"}},
)
async def get_rollout(rollout_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Rollout)
        .where(Rollout.id == rollout_id)
        .options(selectinload(Rollout.items))
    )
    rollout = result.scalar_one_or_none()
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    return rollout


@router.post(
    "/rollouts/{rollout_id}/start",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="启动 Rollout",
)
async def start_rollout(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    if rollout.status != RolloutStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"Cannot start rollout in status '{rollout.status}'"
        )
    rollout.status = RolloutStatus.RUNNING
    db.add(rollout)
    await write_audit(
        db,
        action="rollout_started",
        entity_type="rollout",
        entity_id=rollout_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/pause",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="暂停 Rollout",
)
async def pause_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await pause_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/resume",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="恢复 Rollout",
)
async def resume_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await resume_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout


@router.post(
    "/rollouts/{rollout_id}/rollback",
    response_model=RolloutRead,
    tags=["control / rollouts"],
    summary="回滚 Rollout",
)
async def rollback_rollout_endpoint(
    rollout_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rollout = await db.get(Rollout, rollout_id)
    if not rollout:
        raise HTTPException(status_code=404, detail="Rollout not found")
    try:
        rollout = await rollback_rollout(db, rollout, actor=_actor(request))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    await db.refresh(rollout)
    return rollout
