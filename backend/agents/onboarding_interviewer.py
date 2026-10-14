"""OnboardingInterviewer — One turn of the onboarding interview. Given the conversation so far and the."""
import json
from agents.base_agent import BaseAgent


class OnboardingInterviewer(BaseAgent):
    name = "onboarding_interviewer"

    async def interview_turn(self, history: list, profile: dict) -> dict:
        """One turn of the onboarding interview. Given the conversation so far and the
        profile gathered, ask the next question (or wrap up) and extract new fields.
        Returns {reply, done, profile_patch}."""
        system = """أنت مستشار أعمال ذكي في منصة Qualifay لتوليد العملاء وإدارة المبيعات عبر واتساب.
مهمتك: إجراء مقابلة قصيرة وودّية مع صاحب العمل لفهم نشاطه، حتى نبني له النظام كاملاً.
اجمع تدريجياً: اسم النشاط، المجال/الصناعة، ما الذي يبيعه، نطاق الأسعار، المدن المستهدفة،
العميل المثالي (الصناعة/الحجم/المنصب)، مشاكل العميل، قيمة العرض (لماذا يختارونه)،
مصادر العملاء الحالية، الهدف الشهري للعملاء، حجم فريق المبيعات، ونبرة التواصل المفضلة.
اطرح سؤالاً واحداً في كل مرة، بلغة صاحب العمل نفسها. خصّص الأسئلة حسب المجال
(مثلاً: مقاولات → المناقصات؛ عيادة → الحجوزات).
عندما تجمع ما يكفي (8+ حقول)، اجعل done=true وقدّم ملخصاً ودوداً.
أعد فقط JSON صالح:
{
  "reply": "ردّك/سؤالك التالي بلغة صاحب العمل",
  "done": true|false,
  "profile_patch": { الحقول الجديدة أو المحدّثة فقط، بمفاتيح إنجليزية: business_name, industry, sells, price_range, cities, ideal_customer, pain_points, value_prop, current_sources, monthly_lead_target, team_size, tone, recommended_autonomy(full|copilot|manual) }
}"""
        convo = "\n".join([f"{m.get('role')}: {m.get('content','')}" for m in history[-12:]])
        prompt = f"الملف المجمّع حتى الآن:\n{json.dumps(profile, ensure_ascii=False)}\n\nالمحادثة:\n{convo}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=700,
        )
        return self._parse_json(result, {
            "reply": "عذراً، لم أستطع المتابعة الآن. هل يمكنك إعادة صياغة إجابتك؟",
            "done": False, "profile_patch": {},
        })

    run = interview_turn
