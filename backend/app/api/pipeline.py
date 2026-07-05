"""Pipeline / Deals API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.models.models import PipelineDeal, Pipeline, PipelineStage

router = APIRouter()


class DealCreate(BaseModel):
    pipeline_id: str
    contact_id: str
    title: str
    stage: str = "lead"
    value: float = 0.0
    currency: str = "USD"
    notes: Optional[str] = None


class DealUpdate(BaseModel):
    stage: Optional[str] = None
    value: Optional[float] = None
    notes: Optional[str] = None
    title: Optional[str] = None


@router.get("/pipelines")
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Pipeline))
    return [{"id": p.id, "name": p.name, "is_default": p.is_default} for p in result.scalars().all()]


@router.post("/pipelines")
async def create_pipeline(name: str, db: AsyncSession = Depends(get_db)):
    p = Pipeline(name=name)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "name": p.name}


@router.get("/deals")
async def list_deals(pipeline_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(PipelineDeal).order_by(PipelineDeal.updated_at.desc())
    if pipeline_id:
        query = query.where(PipelineDeal.pipeline_id == pipeline_id)
    result = await db.execute(query)
    deals = result.scalars().all()
    return [_deal_dict(d) for d in deals]


@router.post("/deals")
async def create_deal(data: DealCreate, db: AsyncSession = Depends(get_db)):
    deal = PipelineDeal(**data.dict())
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return _deal_dict(deal)


@router.patch("/deals/{deal_id}")
async def update_deal(deal_id: str, data: DealUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineDeal).where(PipelineDeal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404)
    for field, value in data.dict(exclude_none=True).items():
        setattr(deal, field, value)
    await db.commit()
    return _deal_dict(deal)


def _deal_dict(d: PipelineDeal) -> dict:
    return {
        "id": d.id,
        "pipeline_id": d.pipeline_id,
        "contact_id": d.contact_id,
        "title": d.title,
        "stage": d.stage.value if d.stage else "lead",
        "value": d.value,
        "currency": d.currency,
        "notes": d.notes,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }
