"""All AI agents, keyed by agent name. Each agent owns its prompt and is routed
through BaseAgent, so models, token tracking and fallbacks are configurable per agent."""
from agents.intent_classifier import IntentClassifier
from agents.quality_gate import QualityGate
from agents.bant_scorer import BANTScorer
from agents.lead_enricher import LeadEnricher
from agents.whatsapp_responder import WhatsAppResponder
from agents.aida_writer import AIDAWriter
from agents.query_expander import QueryExpander
from agents.arabic_translator import ArabicTranslator
from agents.pipeline_analyst import PipelineAnalyst
from agents.buyer_intent_classifier import BuyerIntentClassifier
from agents.sentiment_analyzer import SentimentAnalyzer
from agents.followup_scheduler import FollowUpScheduler
from agents.proposal_writer import ProposalWriter
from agents.campaign_planner import CampaignPlanner
from agents.tender_matcher import TenderMatcher
from agents.competitor_analyst import CompetitorAnalyst
from agents.email_finder import EmailFinder
from agents.consent_checker import ConsentChecker
from agents.reply_suggester import ReplySuggester
from agents.onboarding_interviewer import OnboardingInterviewer
from agents.build_planner import BuildPlanner
from agents.message_supervisor import MessageSupervisor
from agents.learning_extractor import LearningExtractor

# public AIService method name → agent class
AGENT_METHODS = {
    "classify_intent": IntentClassifier,
    "quality_gate": QualityGate,
    "score_bant": BANTScorer,
    "enrich_lead": LeadEnricher,
    "generate_wa_reply": WhatsAppResponder,
    "write_aida_message": AIDAWriter,
    "expand_search_queries": QueryExpander,
    "translate_arabic": ArabicTranslator,
    "analyze_conversation_for_pipeline": PipelineAnalyst,
    "classify_buyer_intent": BuyerIntentClassifier,
    "analyze_sentiment": SentimentAnalyzer,
    "schedule_followup": FollowUpScheduler,
    "write_proposal": ProposalWriter,
    "plan_campaign": CampaignPlanner,
    "match_tender": TenderMatcher,
    "analyze_competitor_ad": CompetitorAnalyst,
    "find_email_patterns": EmailFinder,
    "check_consent_compliance": ConsentChecker,
    "suggest_replies": ReplySuggester,
    "interview_turn": OnboardingInterviewer,
    "generate_build_plan": BuildPlanner,
    "supervise_message": MessageSupervisor,
    "extract_learning": LearningExtractor,
}
