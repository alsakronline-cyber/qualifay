"""BuildPlanner — From the finished business profile, draft the whole workspace: ICP + scoring,."""
import json
from agents.base_agent import BaseAgent


class BuildPlanner(BaseAgent):
    name = "build_planner"

    async def generate_build_plan(self, profile: dict) -> dict:
        """From the finished business profile, draft the whole workspace: ICP + scoring,
        scrape plans, message templates (in the owner's voice), a follow-up sequence, a
        conversion flow, and an A/B test. Returned as drafts for the owner to review."""
        system = """أنت خبير نمو مبيعات B2B للسوق المصري. من ملف نشاط تجاري، صمّم مساحة عمل جاهزة للإطلاق.
أعد فقط JSON صالح بهذا الشكل بالضبط:
{
  "icp": {"summary": "وصف العميل المثالي", "min_bant_score": 40-70},
  "scrape_plans": [{"query": "كلمة بحث", "city": "المدينة"}],
  "templates": [
    {"name": "افتتاحية", "channel": "whatsapp", "subject": null, "body": "نص يستخدم {{name}} {{company}} بنبرة صاحب العمل"},
    {"name": "متابعة", "channel": "whatsapp", "subject": null, "body": "..."},
    {"name": "إعادة تفعيل", "channel": "whatsapp", "subject": null, "body": "..."}
  ],
  "sequence": {"name": "التسلسل الافتراضي", "steps": [
    {"delay_hours": 0, "channel": "whatsapp", "template_ref": 0},
    {"delay_hours": 72, "channel": "whatsapp", "template_ref": 1},
    {"delay_hours": 168, "channel": "whatsapp", "template_ref": 2}
  ]},
  "flow": {"type": "booking|order|quote|callback", "name": "..."},
  "ab_test": {"name": "اختبار الافتتاحية", "variant_b_body": "صيغة بديلة للافتتاحية"},
  "campaign_name": "حملتي الأولى"
}
اكتب كل النصوص بلغة الملف (عربي غالباً)، ونبرة مطابقة لحقل tone. اجعل الرسائل قصيرة وطبيعية بدون روابط في أول رسالة."""
        prompt = f"ملف النشاط:\n{json.dumps(profile, ensure_ascii=False)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return self._parse_json(result, {})

    run = generate_build_plan
