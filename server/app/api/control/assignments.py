"""Control API – Agent-Cert assignment endpoints (including batch deploy)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.database import get_db
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    Certificate,
    ExternalCertificate,
)
from app.schemas import (
    AgentCertAssignRequest,
    AgentCertAssignmentRead,
    BatchAssignRequest,
    BatchAssignResult,
    CertRead,
    CertSummary,
)

from app.api.control._helpers import _actor, _ip

router = APIRouter()


@router.post(
    "/agents/{agent_id}/assign-cert",
    response_model=AgentCertAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="为 Agent 分配证书",
    description="""
将外部证书分配给指定 Agent 的某个本地路径。

Agent 下次调用 `/fetch-certs` 时，会对比该路径的证书有效期并拉取更新。

**示例：**
```json
{
  "external_cert_id": "uuid-of-cert",
  "local_path": "/etc/nginx/ssl/api.example.com.crt"
}
```
    """,
)
async def assign_cert_to_agent(
    agent_id: uuid.UUID,
    body: AgentCertAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ext_cert = await db.get(ExternalCertificate, body.external_cert_id)
    if not ext_cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    # Upsert: if assignment for this agent+path already exists, update the cert
    existing_result = await db.execute(
        select(AgentCertAssignment).where(
            AgentCertAssignment.agent_id == agent_id,
            AgentCertAssignment.local_path == body.local_path,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.external_cert_id = body.external_cert_id
        db.add(existing)
        assignment = existing
    else:
        assignment = AgentCertAssignment(
            agent_id=agent_id,
            external_cert_id=body.external_cert_id,
            local_path=body.local_path,
        )
        db.add(assignment)

    await db.flush()

    await write_audit(
        db,
        action="cert_assigned",
        entity_type="agent_cert_assignment",
        entity_id=assignment.id,
        actor=_actor(request),
        details={
            "agent_name": agent.name,
            "local_path": body.local_path,
            "external_cert_name": ext_cert.name,
        },
        ip_address=_ip(request),
    )
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.post(
    "/certs/deploy",
    response_model=BatchAssignResult,
    status_code=status.HTTP_201_CREATED,
    tags=["control / external-certs"],
    summary="批量部署证书到多个 Agent",
    description="""
将外部证书批量部署到多个 Agent。

指定证书 ID、目标 Agent 列表和本地路径，系统会为每个 Agent 创建分配。
Agent 下次心跳时会自动拉取最新证书并部署。
    """,
)
async def batch_deploy_cert(
    body: BatchAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ext_cert = await db.get(ExternalCertificate, body.external_cert_id)
    if not ext_cert:
        raise HTTPException(status_code=404, detail="External certificate not found")

    assignments = []
    success = 0
    failed = 0

    for agent_id in body.agent_ids:
        agent = await db.get(Agent, agent_id)
        if not agent or agent.status != AgentStatus.ACTIVE:
            failed += 1
            continue

        existing_result = await db.execute(
            select(AgentCertAssignment).where(
                AgentCertAssignment.agent_id == agent_id,
                AgentCertAssignment.local_path == body.local_path,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.external_cert_id = body.external_cert_id
            db.add(existing)
            assignments.append(existing)
        else:
            assignment = AgentCertAssignment(
                agent_id=agent_id,
                external_cert_id=body.external_cert_id,
                local_path=body.local_path,
            )
            db.add(assignment)
            assignments.append(assignment)
        success += 1

    if assignments:
        await db.flush()

        await write_audit(
            db,
            action="cert_batch_deployed",
            entity_type="external_certificate",
            entity_id=body.external_cert_id,
            actor=_actor(request),
            details={
                "cert_name": ext_cert.name,
                "target_agents": success,
                "local_path": body.local_path,
            },
            ip_address=_ip(request),
        )

    await db.commit()
    for a in assignments:
        await db.refresh(a)

    return BatchAssignResult(
        success=success,
        failed=failed,
        assignments=assignments,
    )


@router.get(
    "/agents/{agent_id}/assignments",
    response_model=list[AgentCertAssignmentRead],
    tags=["control / external-certs"],
    summary="查看 Agent 的证书分配",
)
async def list_agent_assignments(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(AgentCertAssignment)
        .where(AgentCertAssignment.agent_id == agent_id)
        .order_by(AgentCertAssignment.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete(
    "/agents/{agent_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["control / external-certs"],
    summary="删除证书分配",
)
async def delete_assignment(
    agent_id: uuid.UUID,
    assignment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(AgentCertAssignment, assignment_id)
    if not assignment or assignment.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await write_audit(
        db,
        action="cert_assignment_deleted",
        entity_type="agent_cert_assignment",
        entity_id=assignment_id,
        actor=_actor(request),
        ip_address=_ip(request),
    )
    await db.delete(assignment)
    await db.commit()


# ===========================================================================
# Certificates (audit records)
# ===========================================================================


@router.get(
    "/agents/{agent_id}/certs",
    response_model=list[CertSummary],
    tags=["control / certificates"],
    summary="Agent 证书历史",
    responses={404: {"description": "Agent 不存在"}},
)
async def list_agent_certs(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Certificate)
        .where(Certificate.agent_id == agent_id)
        .order_by(Certificate.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/certs/{cert_id}",
    response_model=CertRead,
    tags=["control / certificates"],
    summary="查询单张证书",
    responses={404: {"description": "证书不存在"}},
)
async def get_cert(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cert = await db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert
