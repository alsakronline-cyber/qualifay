"""AI endpoints — suggest replies, summarize, etc."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.services.ai_service import ai_service

router = APIRouter()


class SuggestRequest(BaseModel):
    message: str
    history: List[dict] = []


class SummarizeRequest(BaseModel):
    contact_name: str
    messages: List[dict]


@router.post("/suggest-replies")
async def suggest_replies(req: SuggestRequest):
    suggestions = await ai_service.suggest_reply(req.message, req.history)
    return {"suggestions": suggestions}


@router.post("/summarize-contact")
async def summarize_contact(req: SummarizeRequest):
    summary = await ai_service.summarize_contact(req.contact_name, req.messages)
    return {"summary": summary}


@router.post("/classify-intent")
async def classify_intent(message: str, contact_name: str = ""):
    result = await ai_service.classify_intent(message, contact_name)
    return result
