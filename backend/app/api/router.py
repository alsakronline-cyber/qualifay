"""
API Router — all routes aggregated
"""
from fastapi import APIRouter
from app.api import (
    auth,
    webhook,
    leads,
    conversations,
    messages,
    instances,
    dashboard,
    notifications,
    scrape,
    agent,
    activity,
    email,
    templates,
    sequences,
    flows,
    team,
    webhooks_config,
    monitoring,
    ab_tests,
    campaigns,
    onboarding,
    agent_runs,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(webhook.router, prefix="/webhook", tags=["Webhooks"])
api_router.include_router(leads.router, prefix="/leads", tags=["Leads"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(messages.router, prefix="/messages", tags=["Messages"])
api_router.include_router(instances.router, prefix="/instances", tags=["WhatsApp Instances"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(scrape.router, prefix="/scrape", tags=["Scraping"])
api_router.include_router(agent.router, prefix="/agent", tags=["Agent Automation"])
api_router.include_router(activity.router, prefix="/activity", tags=["Activity"])
api_router.include_router(email.router, prefix="/email", tags=["Email"])
api_router.include_router(templates.router, prefix="/templates", tags=["Templates"])
api_router.include_router(sequences.router, prefix="/sequences", tags=["Sequences"])
api_router.include_router(flows.router, prefix="/flows", tags=["Flows"])
api_router.include_router(team.router, prefix="/team", tags=["Team"])
api_router.include_router(webhooks_config.router, prefix="/webhooks", tags=["Webhooks Config"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(ab_tests.router, prefix="/ab-tests", tags=["A/B Testing"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Onboarding"])
api_router.include_router(agent_runs.router, prefix="/agent-runs", tags=["Agent Activity"])
