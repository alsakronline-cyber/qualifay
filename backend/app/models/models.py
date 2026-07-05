"""
Qualifay B2B Lead Generation SaaS — SQLAlchemy Models
Multi-tenant architecture with BANT scoring, WhatsApp warmup, lead pool
"""
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float,
    DateTime, ForeignKey, JSON, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────

class Plan(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    growth = "growth"
    agency = "agency"


class LeadSource(str, enum.Enum):
    google_maps = "google_maps"
    linkedin = "linkedin"
    apollo = "apollo"
    web_scrape = "web_scrape"
    manual = "manual"
    pool = "pool"
    referral = "referral"
    inbound_wa = "inbound_wa"
    tender = "tender"
    facebook = "facebook"
    directories = "directories"
    enrichment = "enrichment"
    competitor_ads = "competitor_ads"
    yellowpages = "yellowpages"


class LeadStage(str, enum.Enum):
    new = "new"
    qualifying = "qualifying"
    pending_review = "pending_review"
    approved = "approved"
    outreach = "outreach"
    replied = "replied"
    meeting = "meeting"
    proposal = "proposal"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"
    archived = "archived"
    manual = "manual"


class LeadStatus(str, enum.Enum):
    active = "active"
    unsubscribed = "unsubscribed"
    invalid = "invalid"
    duplicate = "duplicate"


class ConversationStatus(str, enum.Enum):
    open = "open"
    pending = "pending"
    resolved = "resolved"
    ai_handling = "ai_handling"


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class NotificationType(str, enum.Enum):
    leads_ready = "leads_ready"
    wa_limit = "wa_limit"
    wa_warmup = "wa_warmup"
    wa_connected = "wa_connected"
    wa_disconnected = "wa_disconnected"
    consent_issue = "consent_issue"
    campaign_done = "campaign_done"
    pool_match = "pool_match"
    system = "system"


# ─── Tenant ───────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=gen_uuid)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    plan = Column(SAEnum(Plan), default=Plan.trial, nullable=False)
    language = Column(String, default="ar")
    trial_ends_at = Column(DateTime, nullable=True)
    auto_approve = Column(Boolean, default=False)
    min_bant_score = Column(Integer, default=50)
    contribute_to_pool = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Browser-extension automation agent (LinkedIn/Facebook sourcing — see AgentTask)
    agent_key = Column(String, unique=True, nullable=True, index=True)
    agent_daily_cap_linkedin = Column(Integer, default=80)
    agent_daily_cap_facebook = Column(Integer, default=150)
    agent_min_interval_seconds = Column(Integer, default=45)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="tenant", cascade="all, delete-orphan")
    wa_instances = relationship("WaInstance", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="tenant", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    scrape_jobs = relationship("ScrapeJob", back_populates="tenant", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="tenant", cascade="all, delete-orphan")


# ─── User ─────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_tenant_admin = Column(Boolean, default=False)
    language = Column(String, default="ar")
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="users")
    assigned_leads = relationship("Lead", back_populates="assigned_user", foreign_keys="Lead.assigned_to")
    notifications = relationship("Notification", back_populates="user")


# ─── Lead ─────────────────────────────────────────────────────

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), default=LeadSource.manual)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True, index=True)          # E.164
    email = Column(String, nullable=True)
    company = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)
    city = Column(String, nullable=True)
    governorate = Column(String, nullable=True)
    website = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)

    # BANT
    bant_score = Column(Integer, default=0)                    # 0-100
    bant_budget = Column(String, nullable=True)
    bant_authority = Column(String, nullable=True)
    bant_need = Column(String, nullable=True)
    bant_timeline = Column(String, nullable=True)
    bant_reason = Column(Text, nullable=True)

    stage = Column(SAEnum(LeadStage), default=LeadStage.new)
    status = Column(SAEnum(LeadStatus), default=LeadStatus.active)
    language = Column(String, default="ar")

    # Consent (GDPR/PDPA compliance)
    consent_at = Column(DateTime, nullable=True)
    consent_method = Column(String, nullable=True)
    consent_ip = Column(String, nullable=True)

    # Lead Pool
    pool_contributed = Column(Boolean, default=False)
    pool_entry_id = Column(String, ForeignKey("lead_pool.id"), nullable=True)

    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)
    raw_data = Column(JSON, default=dict)
    ai_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="leads")
    assigned_user = relationship("User", back_populates="assigned_leads", foreign_keys=[assigned_to])
    pool_entry = relationship("LeadPool", foreign_keys=[pool_entry_id])
    consent_logs = relationship("ConsentLog", back_populates="lead", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="lead")


# ─── Lead Pool ────────────────────────────────────────────────

class LeadPool(Base):
    """Shared anonymised pool — no personal data (phone/email stripped)."""
    __tablename__ = "lead_pool"

    id = Column(String, primary_key=True, default=gen_uuid)
    contributed_by = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    company = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)
    city = Column(String, nullable=True)
    governorate = Column(String, nullable=True)
    website = Column(String, nullable=True)
    source = Column(SAEnum(LeadSource), nullable=True)
    bant_score = Column(Integer, default=0)
    claimed_count = Column(Integer, default=0)
    verified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    contributor = relationship("Tenant", foreign_keys=[contributed_by])


# ─── WaInstance ───────────────────────────────────────────────

class WaInstance(Base):
    __tablename__ = "wa_instances"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    instance_name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    status = Column(String, default="disconnected")
    phone_number = Column(String, nullable=True)
    day_of_life = Column(Integer, default=0)
    daily_wa_cap = Column(Integer, default=10)
    sent_today_wa = Column(Integer, default=0)
    sent_today_email = Column(Integer, default=0)
    last_reset_at = Column(DateTime, nullable=True)
    warmup_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="wa_instances")
    conversations = relationship("Conversation", back_populates="wa_instance")
    campaigns = relationship("Campaign", back_populates="wa_instance")


# ─── Conversation ─────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", "wa_jid", name="uq_conversation_tenant_instance_jid"),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    wa_instance_id = Column(String, ForeignKey("wa_instances.id"), nullable=True)
    instance_name = Column(String, nullable=False)
    wa_jid = Column(String, nullable=False, index=True)
    contact_name = Column(String, nullable=True)
    status = Column(SAEnum(ConversationStatus), default=ConversationStatus.open)
    ai_enabled = Column(Boolean, default=False)
    last_message = Column(Text, nullable=True)
    unread_count = Column(Integer, default=0)
    sentiment = Column(String, default="neutral")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="conversations")
    lead = relationship("Lead", back_populates="conversations")
    wa_instance = relationship("WaInstance", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at")


# ─── Message ──────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    wa_message_id = Column(String, nullable=True, index=True)
    direction = Column(SAEnum(MessageDirection), nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String, default="text")
    media_url = Column(String, nullable=True)
    is_ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)
    transcription = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


# ─── ScrapeJob ────────────────────────────────────────────────

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), nullable=False)
    config = Column(JSON, default=dict)
    status = Column(String, default="pending")          # pending, running, paused, done, failed
    leads_found = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    paused_until = Column(DateTime, nullable=True)
    celery_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="scrape_jobs")


# ─── ScrapeSchedule (daily automatic search) ──────────────────

class ScrapeSchedule(Base):
    __tablename__ = "scrape_schedules"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), nullable=False)
    config = Column(JSON, default=dict)          # query, location, industry, max_results
    hour_cairo = Column(Integer, default=9)      # 0-23, hour of day in Africa/Cairo
    enabled = Column(Boolean, default=True)
    monthly_cap = Column(Integer, default=1000)  # stop scheduling once this many leads pulled this month
    monthly_count = Column(Integer, default=0)   # leads pulled by this schedule in the current month
    month_key = Column(String, nullable=True)    # "YYYY-MM" the monthly_count applies to
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


# ─── AgentTask (browser-extension automation — Option A) ──────
#
# The Chrome extension (LinkedIn contact discovery + Facebook group/page buyer-intent
# watching) polls GET /api/v1/agent/tasks/next on its own machine via chrome.alarms —
# no human clicks required after the one-time setup. Each row is one unit of work; a
# "recurring" task (e.g. "watch this FB group") re-arms itself via next_eligible_at
# instead of terminating, so it keeps firing on a cadence without a new row per run.

class AgentPlatform(str, enum.Enum):
    linkedin = "linkedin"
    facebook = "facebook"


class AgentTaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    error = "error"


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    platform = Column(SAEnum(AgentPlatform), nullable=False)
    type = Column(String, nullable=False)  # "linkedin_search" | "facebook_group_watch" | "facebook_page_watch"
    params = Column(JSON, default=dict)    # query/location/group_id/page_id/max_results
    status = Column(String, default="pending", index=True)
    recurring = Column(Boolean, default=False)
    interval_minutes = Column(Integer, default=120)  # re-eligibility gap for recurring tasks
    next_eligible_at = Column(DateTime, nullable=True)
    result_count = Column(Integer, default=0)
    total_results = Column(Integer, default=0)  # cumulative across all recurring runs
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ─── Campaign ─────────────────────────────────────────────────

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    wa_instance_id = Column(String, ForeignKey("wa_instances.id"), nullable=True)
    message_template = Column(Text, nullable=True)
    status = Column(String, default="draft")            # draft, running, paused, done
    target_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    channel = Column(String, default="whatsapp")        # whatsapp, email, both
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="campaigns")
    wa_instance = relationship("WaInstance", back_populates="campaigns")


# ─── ConsentLog ───────────────────────────────────────────────

class ConsentLog(Base):
    __tablename__ = "consent_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    method = Column(String, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    consent_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    lead = relationship("Lead", back_populates="consent_logs")


# ─── Notification ─────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    data = Column(JSON, default=dict)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="notifications")
    user = relationship("User", back_populates="notifications")


# ─── Subscription ─────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, unique=True)
    provider = Column(String, nullable=True)                    # paymob, fawry, stripe
    external_id = Column(String, nullable=True)
    status = Column(String, default="trial")                    # trial, active, past_due, cancelled
    currency = Column(String, default="EGP")
    plan = Column(SAEnum(Plan), default=Plan.trial)
    current_period_end = Column(DateTime, nullable=True)
    eta_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="subscription")


# ─── Activity Log ─────────────────────────────────────────────

class ActivityType(str, enum.Enum):
    lead_scraped = "lead_scraped"
    lead_qualified = "lead_qualified"
    lead_approved = "lead_approved"
    lead_rejected = "lead_rejected"
    lead_updated = "lead_updated"
    message_sent = "message_sent"
    message_received = "message_received"
    ai_suggested = "ai_suggested"
    ai_sent = "ai_sent"
    scrape_started = "scrape_started"
    scrape_completed = "scrape_completed"
    instance_connected = "instance_connected"
    instance_disconnected = "instance_disconnected"
    appointment_booked = "appointment_booked"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True)
    activity_type = Column(SAEnum(ActivityType), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String, nullable=True, index=True)
    summary = Column(String(500), nullable=False)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
