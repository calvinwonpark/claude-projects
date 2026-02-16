# Sample Questions

Use these prompts to demo routing, RAG grounding, citations, and tool execution.

## General Founder

- I am a solo founder. How do I get my first 10 users?
- We have early traction but poor retention. What should we fix first?
- How should I prioritize product, sales, and fundraising over the next 12 weeks?
- Give me a 30-day execution plan to validate PMF for a B2B workflow tool.

## Tech Advisor

- How should we design our API for long-term scale?
- Should we start with a modular monolith or microservices?
- What security controls should we implement before onboarding enterprise customers?
- What observability stack do you recommend for a small team?
- How should we structure request IDs, tracing, and auditability in our backend?

## Marketing Advisor

- What is a practical GTM strategy for an SMB SaaS startup?
- Which acquisition channel should we test first with a limited budget?
- How can I improve landing page copy to increase activation?
- Give me 5 messaging angles for a product that reduces support workload.
- How should we design weekly growth experiments with clear success metrics?

## Investor Advisor

- What should I include in a pre-seed pitch deck?
- Which KPIs should I report monthly to investors?
- How do I decide the right time to raise our next round?
- Help me craft a strong fundraising narrative for a B2B AI startup.
- What investor concerns should I preempt in a seed meeting?

## Tool-Use Demos

- Estimate TAM for this startup idea in Korea.
- Give me a quick competitor summary for this category.
- Calculate unit economics with price 49, COGS 8, CAC 120.
- Compare two pricing options and estimate CAC payback period.

### Guaranteed Tool-Call Triggers

- **market_size_lookup**: "Estimate TAM/SAM/SOM for an AI customer support startup in Korea."
- **unit_economics_calculator**: "My price is 49, COGS is 8, CAC is 120, monthly churn is 3%. Calculate LTV and CAC payback."
- **competitor_summary**: "Give me a competitor summary for AI helpdesk tools and compare alternatives."

## Routing Strategy Demos

Use these to explicitly demo router behavior when `ROUTER_STRATEGY=auto`.

### winner_take_all (high confidence + large gap)

- I need a pre-seed pitch deck outline and fundraising narrative.
- What security controls should we implement before SOC 2?
- Give me a GTM channel test plan for an SMB SaaS launch.

### consult_then_decide (clear lead, but mixed intent)

- For our seed deck, should we lead with technical moat or traction story?
- We need better onboarding: should we prioritize product UX fixes or lifecycle marketing first?
- For enterprise sales, what should we improve first: API reliability, pricing, or messaging?

### ensemble_vote (ambiguous / cross-functional)

- We are missing growth targets and burn is high. What should we do in the next 90 days?
- How should a 5-person startup split priorities across product, GTM, and fundraising this quarter?
- Our activation is low and runway is short. Give a single plan covering tech, marketing, and investor updates.

## Korean Prompts (한국어)

- 1인 창업자인데 첫 10명의 유저를 어떻게 확보하면 좋을까요?
- 초기 GTM 전략을 4주 실행 계획으로 만들어주세요.
- 투자자에게 보여줄 KPI 우선순위를 정리해주세요.
- 프리시드 피치덱에 꼭 들어가야 할 슬라이드는 무엇인가요?
- 우리 서비스의 TAM을 대략 추정해 주세요.
- CAC와 회수기간을 간단히 계산해 주세요. (가격 39, 원가 7, CAC 90)

## Citation / Grounding Checks

- Answer using only retrieved sources and cite every factual paragraph.
- If evidence is weak, explicitly say what document is missing.
- Give me recommendations and include inline citations like [doc:<id>].

