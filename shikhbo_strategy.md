---
name: shikhbo_strategy
description: Use when generating or refining the 5 Lovable prompts for Shikhbo. Defines the prompt structure, the Lovable+HuggingFace architecture split, the 5-prompt sequence, credit budget, and the Shikhbo-specific requirements (bilingual, RAG grounding, curriculum isolation, tiers).
---

# Shikhbo — Lovable Prompt Strategy

## THE GOLDEN RULE
Lovable builds the **web app** (React + Supabase). The **AI** (RAG, LLM, embeddings, vision) lives on **Hugging Face Spaces** and is called via a Supabase Edge Function. Never ask Lovable to run models. The user has 10GB Mac space — all models are cloud-hosted on HF, never local.

## THE 5-PROMPT SEQUENCE
1. **Foundation** — schema, auth (email + Google), app shell matching the prototype. ~18 credits.
2. **Chat Engine** — message CRUD, history, voice STT, browser TTS, sources panel, placeholder Edge Function in the exact shape Prompt 3 will fill. ~18 credits.
3. **AI Integration** — wire ask-shikhbo to the HF /chat API, analyze-image to HF /vision (premium), rate limiting, response cache. ~16 credits. (Most critical prompt.)
4. **Subscription & Fortress** — Stripe, premium gating (server-side), GDPR (minor-friendly), audit logs, Sentry, PostHog, admin. ~18 credits.
5. **Polish & Growth** — onboarding, interactive Quiz mode, streaks, mobile, SEO, A/B, retention email. ~14 credits.

Total ~90 of 100 credits. Keep prompts tight to preserve the ~10-credit buffer.

## PROMPT STRUCTURE (every prompt)
```
## CONTEXT (what's built so far, what this adds)
## OBJECTIVE (one sentence)
## DATABASE SCHEMA (exact tables/columns/RLS, where relevant)
## [FEATURE SECTIONS] (functionality with specifics)
## EDGE CASES & VALIDATION
## SECURITY REQUIREMENTS
## SUCCESS CRITERIA
```

## SHIKHBO-SPECIFIC REQUIREMENTS TO BAKE INTO EVERY PROMPT
- **Bilingual:** Bengali + English UI and responses. Bengali is the differentiator — never an afterthought.
- **Grounded + graceful fallback:** answer from textbook chunks with citations; if not found, say so clearly then give a labeled general explanation.
- **Curriculum isolation:** NCTB ICT vs Edexcel Physics must never mix in retrieval.
- **Four modes:** Normal, Simple, Quiz, Step-by-Step — a prompt-template switch over the same retrieval.
- **Two tiers:** free (text+voice, 30/day, browser TTS) vs premium (image upload, enhanced model, cloud Bengali TTS, unlimited). Gate server-side.
- **Match the prototype UI:** login hero "Learn smarter, not harder"; chat with Subject (ICT/Bangla/Physics) + Response Quality (Fast/Enhanced) + Mode selectors; bilingual + dark/light toggles; sources dropdown; mic + attach + send; context tag row.

## CREDIT DISCIPLINE
Each prompt must complete in one Plan+Build cycle. In Plan Mode, review the plan before approving — if a table or RLS policy is missing, edit the plan (free) rather than approving and fixing later (costs a rebuild). Use the free Security Check before Publish.

## SELF-CHECK BEFORE SUBMITTING ANY PROMPT
- [ ] Treats AI as external HF API (not built in Lovable)?
- [ ] HF/Stripe secrets server-side only?
- [ ] Bengali handling explicit?
- [ ] Grounded/fallback citation behavior present?
- [ ] Curriculum isolation maintained?
- [ ] Premium gating server-side?
- [ ] Scoped to ~one credit cycle?
- [ ] References previous prompt's output?
