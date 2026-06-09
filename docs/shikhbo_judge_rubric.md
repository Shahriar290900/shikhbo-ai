---
name: shikhbo_judge_rubric
description: Use when evaluating or scoring the 5 Shikhbo Lovable prompts. EdTech-adapted rubric covering technical depth, production readiness, AI-integration correctness, security/compliance, and execution clarity, with the Lovable+HuggingFace split in mind.
---

# Shikhbo — Prompt Evaluation Rubric
## For scoring the 5 Lovable prompts that build Shikhbo

---

## WHAT MAKES SHIKHBO PROMPTS DIFFERENT FROM GENERIC ONES
Shikhbo has a unique architecture the judge must check for: **Lovable builds the web app; the AI lives on Hugging Face.** A prompt that asks Lovable to "run the LLM" or "build the RAG pipeline" is WRONG and must be penalized — Lovable cannot do that. Correct prompts treat the AI as an external API called via an Edge Function.

---

## SCORING CRITERIA (each prompt scored 0–100)

### 1. Technical Depth (30 pts)
- Explicit Supabase schema (tables, columns, types, RLS) where relevant
- Edge Function contracts defined (input/output shapes)
- Clear state management for the chat (subject/mode/quality)
- Bengali/English bilingual handling specified

### 2. Production Readiness (25 pts)
- No placeholders/deferrals (except the intentional Prompt-2 placeholder that Prompt 3 replaces — that is correct sequencing, not a deferral)
- All UI states: loading, empty, error, the grounded-vs-fallback distinction
- Error handling for HF cold starts and timeouts

### 3. AI-Integration Correctness (20 pts) — Shikhbo-specific
- Does the prompt correctly treat the AI as an EXTERNAL HF API, not something Lovable builds?
- Is the HF token kept server-side (Supabase secret), never in the client?
- Are mode/quality/curriculum/subject passed through to the AI correctly?
- Is the grounded/fallback citation behavior preserved?
- Is curriculum isolation maintained (ICT vs Physics not mixed)?

### 4. Security & Compliance (15 pts)
- RLS on all user-data tables
- Premium gating enforced server-side, not just hidden in UI
- GDPR (minor-friendly defaults, consent, export, deletion)
- Stripe webhook signature verification + idempotency
- Secrets in Supabase, never frontend

### 5. Execution Clarity (10 pts)
- Could Lovable execute this with no follow-up?
- Correct scope for one credit cycle (~15-20 credits)
- References the previous prompt's output (cumulative build)
- UI spec matches the actual Shikhbo prototype screens

---

## CREDIT-AWARENESS CHECK (Shikhbo has only 100 credits)
Penalize prompts that are so broad they'd need multiple rebuilds (wasting credits). Reward prompts scoped to complete in a single Plan+Build cycle. Flag any prompt likely to exceed ~20 credits.

---

## RED FLAGS (specific to Shikhbo)
- 🚩 Asks Lovable to host/run the LLM, embeddings, FAISS, or RAG → architectural error, major penalty
- 🚩 HF token or Stripe secret placed in frontend code
- 🚩 No grounded/fallback distinction in the chat UI (loses the trust differentiator)
- 🚩 Bengali handling ignored (it's the core value prop)
- 🚩 Premium features gated only in UI, not server-side
- 🚩 No curriculum isolation (ICT answers leaking Physics content)
- 🚩 Prompt 1 missing Google OAuth setup
- 🚩 Scope so large it would burn >25 credits in one build

---

## QUALIFICATION
- Per-prompt position weights: P1=25%, P2=20%, P3=25% (AI integration is critical), P4=20%, P5=10%
- Final ≥ 75 = strong; 60-74 = needs work; <60 = rework

---

## JUDGE OUTPUT FORMAT
Return JSON:
```json
{
  "prompt_scores": [
    {"prompt": 1, "technical_depth": N, "production_readiness": N, "ai_integration": N, "security": N, "clarity": N, "total": N, "credit_risk": "low|medium|high", "gaps": ["..."]}
  ],
  "red_flags": ["..."],
  "architecture_check": "PASS|FAIL — does it correctly split Lovable vs HF?",
  "final_score": N,
  "qualification": "STRONG|NEEDS_WORK|REWORK",
  "top_strengths": ["..."],
  "critical_gaps": ["..."],
  "credit_budget_estimate": "X of 100 credits"
}
```
