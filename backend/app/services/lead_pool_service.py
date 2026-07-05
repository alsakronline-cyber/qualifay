"""
LeadPoolService — Shared anonymised B2B lead pool
Tenants contribute qualified leads (BANT >= 60), others can claim them
Personal data (phone, email) is stripped before contributing
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, not_, exists

logger = logging.getLogger(__name__)

POOL_BANT_MIN = 60
POOL_EXPIRY_DAYS = 90
POOL_MAX_CLAIMS = 3


class LeadPoolService:

    async def contribute(self, lead_id: str, db: AsyncSession) -> Optional[dict]:
        """
        Contribute a lead to the shared pool.
        Requirements: bant_score >= 60, not already contributed, has company info.
        Personal data (phone, email) is NOT stored in the pool.
        Returns pool entry dict or None.
        """
        from app.models.models import Lead, LeadPool

        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            logger.warning(f"Lead {lead_id} not found for pool contribution")
            return None

        if (lead.bant_score or 0) < POOL_BANT_MIN:
            logger.info(f"Lead {lead_id} BANT score {lead.bant_score} below pool minimum {POOL_BANT_MIN}")
            return None

        if lead.pool_contributed:
            logger.info(f"Lead {lead_id} already contributed to pool")
            return None

        if not lead.company and not lead.industry:
            logger.info(f"Lead {lead_id} has no company/industry — skipping pool contribution")
            return None

        # Create pool entry — no personal data
        pool_entry = LeadPool(
            contributed_by=lead.tenant_id,
            company=lead.company,
            industry=lead.industry,
            company_size=lead.company_size,
            city=lead.city,
            governorate=lead.governorate,
            website=lead.website,
            source=lead.source,
            bant_score=lead.bant_score,
            claimed_count=0,
            expires_at=datetime.utcnow() + timedelta(days=POOL_EXPIRY_DAYS),
        )
        db.add(pool_entry)
        await db.flush()

        # Mark lead as contributed
        lead.pool_contributed = True
        lead.pool_entry_id = pool_entry.id
        await db.commit()

        logger.info(f"Lead {lead_id} contributed to pool as {pool_entry.id}")
        return {
            "pool_id": pool_entry.id,
            "company": pool_entry.company,
            "industry": pool_entry.industry,
            "bant_score": pool_entry.bant_score,
        }

    async def search(
        self,
        db: AsyncSession,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        min_score: int = 0,
        limit: int = 20,
        claiming_tenant_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Search pool for available leads.
        Excludes: expired entries, entries contributed by this tenant,
                  entries already claimed by this tenant, entries with claim_count >= 3.
        """
        from app.models.models import LeadPool, Lead

        query = select(LeadPool).where(
            and_(
                LeadPool.expires_at > datetime.utcnow(),
                LeadPool.claimed_count < POOL_MAX_CLAIMS,
                LeadPool.bant_score >= min_score,
            )
        )

        if claiming_tenant_id:
            # Exclude entries contributed by this tenant
            query = query.where(LeadPool.contributed_by != claiming_tenant_id)

            # Exclude entries already claimed by this tenant
            already_claimed = select(Lead.pool_entry_id).where(
                and_(
                    Lead.tenant_id == claiming_tenant_id,
                    Lead.pool_entry_id.isnot(None),
                )
            )
            query = query.where(not_(LeadPool.id.in_(already_claimed)))

        if industry:
            query = query.where(LeadPool.industry == industry)

        if city:
            query = query.where(LeadPool.city.ilike(f"%{city}%"))

        query = query.order_by(LeadPool.bant_score.desc()).limit(limit)
        result = await db.execute(query)
        entries = result.scalars().all()

        return [
            {
                "id": e.id,
                "company": e.company,
                "industry": e.industry,
                "company_size": e.company_size,
                "city": e.city,
                "governorate": e.governorate,
                "website": e.website,
                "source": e.source.value if e.source else None,
                "bant_score": e.bant_score,
                "claimed_count": e.claimed_count,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            }
            for e in entries
        ]

    async def claim(self, pool_id: str, tenant_id: str, db: AsyncSession) -> Optional[dict]:
        """
        Claim a pool entry for a tenant.
        Creates a new Lead record in the tenant's namespace with stage=new, source=pool.
        Increments claimed_count on the pool entry.
        Returns the new lead dict or None.
        """
        from app.models.models import LeadPool, Lead, LeadStage, LeadSource

        # Lock and fetch pool entry
        result = await db.execute(
            select(LeadPool).where(
                and_(
                    LeadPool.id == pool_id,
                    LeadPool.expires_at > datetime.utcnow(),
                    LeadPool.claimed_count < POOL_MAX_CLAIMS,
                    LeadPool.contributed_by != tenant_id,
                )
            )
        )
        pool_entry = result.scalar_one_or_none()
        if not pool_entry:
            logger.warning(f"Pool entry {pool_id} not available for tenant {tenant_id}")
            return None

        # Check not already claimed by this tenant
        existing = await db.execute(
            select(Lead).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.pool_entry_id == pool_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.info(f"Tenant {tenant_id} already claimed pool entry {pool_id}")
            return None

        # Create new lead for this tenant
        new_lead = Lead(
            tenant_id=tenant_id,
            source=LeadSource.pool,
            stage=LeadStage.new,
            company=pool_entry.company,
            industry=pool_entry.industry,
            company_size=pool_entry.company_size,
            city=pool_entry.city,
            governorate=pool_entry.governorate,
            website=pool_entry.website,
            bant_score=pool_entry.bant_score,
            pool_contributed=False,
            pool_entry_id=pool_id,
            raw_data={
                "claimed_from_pool": True,
                "pool_entry_id": pool_id,
                "original_bant_score": pool_entry.bant_score,
            },
        )
        db.add(new_lead)

        # Increment claimed_count
        pool_entry.claimed_count += 1
        await db.commit()
        await db.refresh(new_lead)

        logger.info(f"Tenant {tenant_id} claimed pool entry {pool_id} → lead {new_lead.id}")
        return {
            "lead_id": new_lead.id,
            "company": new_lead.company,
            "industry": new_lead.industry,
            "bant_score": new_lead.bant_score,
            "stage": new_lead.stage.value,
        }


lead_pool_service = LeadPoolService()
