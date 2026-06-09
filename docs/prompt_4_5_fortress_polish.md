# SHIKHBO — LOVABLE PROMPT 4: SUBSCRIPTION & FORTRESS
## Stripe Billing · Feature Gating · GDPR · Observability · Admin

---

## CONTEXT
Building on Shikhbo Prompts 1–3 (auth, chat, live AI, rate limiting). This prompt adds the subscription business model (free vs premium), Stripe billing, GDPR/CCPA compliance, audit logging, error tracking, analytics, and an admin dashboard — making Shikhbo a real product, not just a demo.

## OBJECTIVE
Implement Stripe subscription checkout and webhooks with idempotency, premium feature gating, GDPR data export/deletion, consent management, audit logging, Sentry error tracking, PostHog analytics, and an admin dashboard.

---

## STRIPE SUBSCRIPTION

### Plans
- **Free:** 30 messages/day, voice input, browser TTS, no image upload, fast model only
- **Premium (e.g. ৳200/month or $2/month):** unlimited messages, image/PDF analysis, enhanced model quality, high-quality Bengali cloud TTS, priority

### Edge Function: create-checkout-session
- Verify JWT. Get/create Stripe customer (store stripe_customer_id in subscriptions). Create Checkout Session (mode=subscription, premium price_id, 7-day trial, success_url=/settings?upgraded=true, cancel_url=/settings). Return session.url.

### Edge Function: stripe-webhook
- Verify Stripe-Signature with STRIPE_WEBHOOK_SECRET (reject if invalid)
- Idempotency: check processed_webhooks for event.id, skip if seen
- Handle: customer.subscription.created/updated → UPSERT subscriptions (plan='premium', status, current_period_end); also UPDATE profiles.tier='premium'. customer.subscription.deleted → plan='free', profiles.tier='free'. invoice.payment_failed → status='past_due'. invoice.paid → status='active'.
- INSERT into processed_webhooks after handling.

### TABLE: processed_webhooks
```
id UUID PK DEFAULT gen_random_uuid()
event_id TEXT UNIQUE NOT NULL
event_type TEXT NOT NULL
processed_at TIMESTAMPTZ DEFAULT now()
```

### Edge Function: create-billing-portal
- Stripe billing portal session for managing/canceling subscription.

### Billing UI (/settings, billing section)
- Current plan badge + status. If premium: next billing date, "Manage Billing" → portal. If free: plan comparison + "Upgrade to Premium" → checkout.
- Trial countdown if trialing. Past-due red alert with update-payment link.

---

## PREMIUM FEATURE GATING (enforce server-side)
Gate these on tier='premium' in the relevant Edge Functions (already partly done in Prompt 3):
- Image/PDF analysis (analyze-image returns 403 for free)
- Enhanced model quality (downgraded to fast for free)
- Cloud Bengali TTS (new — premium TTS Edge Function calling a Bengali TTS service; free tier uses browser TTS)
- Unlimited messages (free capped at 30/day)

Every gate also shows a friendly upgrade prompt in the UI, never a dead end.

---

## GDPR / CCPA COMPLIANCE

### Consent banner
On first login after signup: modal with Terms, Privacy, Analytics toggle (default off for under-18 friendliness), Cookies toggle. Save to user_consents with version. Block app until accepted.

### Edge Function: export-user-data
- Returns all user data (profiles, chat_sessions, messages, subscriptions, usage_tracking, user_consents) as downloadable JSON. Rate limit 1/day.

### Edge Function: delete-account
- Requires typed "DELETE" confirmation. Cancel Stripe subscription if active. Soft-delete then schedule hard delete (auth.admin.deleteUser) after 30 days via a scheduled function. Sign out.

### Note on minors
Many users are students under 18. Default analytics consent to OFF, mask all inputs in any session recording, and keep data collection minimal. Add a short, simple-Bengali privacy explanation.

---

## AUDIT LOGGING

### TABLE: audit_logs
```
id UUID PK DEFAULT gen_random_uuid()
user_id UUID references profiles(id)
action TEXT NOT NULL
table_name TEXT
record_id UUID
metadata JSONB
created_at TIMESTAMPTZ DEFAULT now()
```
RLS: admins SELECT only. INSERT via service role. No UPDATE/DELETE (immutable).
Trigger-log INSERT/UPDATE/DELETE on profiles and subscriptions. Also log logins, data exports, account deletions, tier changes.

---

## OBSERVABILITY

### Sentry
Initialize @sentry/react in main.tsx (VITE_SENTRY_DSN, env-based environment, beforeSend strips email/IP for GDPR). Wrap ChatInterface, BillingSettings, ImageUpload in Sentry.ErrorBoundary with friendly fallbacks. Edge Functions log structured errors to console.

### PostHog
Initialize posthog-js (identified_only, maskAllInputs). Only after analytics consent = true. Identify user by id with { tier, curriculum, class_level } (no PII). Track events:
```
user_signed_up { method: 'email'|'google' }
onboarding_completed { curriculum, subject }
message_sent { subject, mode, quality, grounded }
voice_used { language }
image_analyzed { subject }       (premium)
mode_changed { from, to }
upgrade_clicked { trigger: 'limit'|'image_gate'|'quality'|'settings' }
subscription_started { plan, trial }
daily_limit_reached {}
```

---

## ADMIN DASHBOARD (/admin, admin role only)
- Overview: total users, free vs premium counts, daily active users, messages/day chart (Recharts), premium conversion rate
- Users table: email, tier, curriculum, signup date, message count; actions: change tier, view usage
- Usage analytics: most-asked subjects, mode distribution, grounded vs fallback ratio (quality signal for your RAG)
- Audit log viewer with filters

Add `is_admin BOOLEAN DEFAULT FALSE` to profiles; /admin checks it server-side.

---

## EDGE CASES
- Webhook before checkout success row exists: UPSERT handles it
- Premium user cancels: keep premium until current_period_end, then downgrade
- Account deletion with active premium: cancel Stripe first
- Analytics consent withdrawn later: stop PostHog capture immediately
- Export rate limit: 429 with "once per day" message

---

## SECURITY REQUIREMENTS
- STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET in Edge Function secrets only
- Webhook signature verification mandatory
- All premium gates enforced server-side
- Audit logs immutable (no UPDATE/DELETE policy)
- Sentry/PostHog strip PII; analytics gated on consent
- delete-account verifies the requesting user owns the account

---

## SUCCESS CRITERIA
- Free→Premium upgrade via Stripe works; tier updates on webhook within seconds
- Premium features unlock immediately after upgrade; free users see upgrade prompts
- Data export downloads complete JSON; account deletion schedules correctly
- Consent banner blocks app until accepted; analytics respect consent
- Audit log records tier changes and logins
- Admin dashboard shows correct counts and the grounded-vs-fallback ratio

---
---

# SHIKHBO — LOVABLE PROMPT 5: POLISH & GROWTH
## Onboarding · Quiz Mode · Progress · Mobile · SEO · Retention

---

## CONTEXT
Building on Shikhbo Prompts 1–4 (full product with AI, billing, compliance). This final prompt delivers the onboarding experience, a polished Quiz mode, learning progress/streaks, mobile optimization, SEO, A/B testing, and retention — making Shikhbo launch- and demo-ready.

## OBJECTIVE
Build the onboarding wizard, an interactive Quiz mode, a learning progress/streak system, full mobile responsiveness, SEO metadata, PostHog A/B flags on the upgrade CTA, and a retention email via Resend.

---

## ONBOARDING WIZARD (/onboarding — 3 steps)

Step 1 — Welcome + Language: choose বাংলা/English UI. Friendly intro: "তোমার নিজের AI শিক্ষক / Your personal AI tutor."
Step 2 — Curriculum & Class: select curriculum (NCTB / Edexcel A-Level), class (SSC / A-level), default subject (ICT / Bangla / Physics). These set profile fields and the default chat context.
Step 3 — Quick tour: 3 cards explaining Subjects, the four Modes, and voice/image. "Start Learning" → set onboarding_complete=true → /chat with a welcome message.

Track onboarding_completed in PostHog.

---

## QUIZ MODE (polished interactive experience)
When mode='quiz', instead of plain text, render an interactive quiz:
- The HF backend returns quiz questions (MCQ) from the chapter; render each as a card with options
- Student selects an answer → immediate feedback (correct/incorrect) + the explanation from the textbook with source citation
- Score tally at the end: "You scored 7/10 on ICT Chapter 1"
- "Try again" and "Review wrong answers" buttons
- Save quiz attempts to a `quiz_attempts` table (user_id, subject, chapter, score, total, created_at) for progress tracking
- RLS: users see only their own attempts

---

## LEARNING PROGRESS & STREAKS
- Dashboard widget on /chat sidebar or a /progress page:
  - Daily streak counter (consecutive days with at least one question) — drives retention
  - Questions asked this week, by subject (small bar chart)
  - Quiz scores over time
  - "Topics explored" list per subject
- Streak calculation from messages/quiz_attempts dates. Show a flame icon + "৩ দিনের ধারা! / 3-day streak!"

---

## MOBILE OPTIMIZATION
- Sidebar (Subject/Quality/Mode) collapses into a top sheet/drawer on mobile (<640px), toggled by a filter button
- Chat input bar sticky at bottom, keyboard-aware
- Message bubbles full-width on mobile
- Touch targets ≥44px
- Voice and send buttons large and thumb-reachable
- Test at 375px width — no horizontal scroll

---

## SEO METADATA (react-helmet-async)
```
/ — title "শিখবো (Shikhbo) — AI Study Partner for NCTB & A-Level Students" · description "Curriculum-aligned AI tutor for Bangladeshi students. Ask in Bengali or English by text, voice, or photo. Grounded in your textbook."
/auth — "Sign In — Shikhbo"
```
Add og:title, og:description, og:image on landing. Add lang attribute switching with ui_language.

---

## A/B TESTING (PostHog flags)
- Flag `upgrade-cta-copy`: variants 'control' ("Upgrade to Premium") / 'value' ("Unlock unlimited questions + photo solving") / 'student' ("Study without limits — ৳200/mo")
- Apply to the upgrade button shown on daily-limit and image-gate prompts
- Track exposure + upgrade_clicked by variant

---

## RETENTION
- Edge Function send-streak-reminder (scheduled daily): for users with an active streak who haven't asked a question today, send a Resend email "তোমার ধারা ধরে রাখো! / Keep your streak alive — ask one question today." (respect email consent)
- Welcome email on signup via Resend (simple Bengali + English)
- In-app: gentle nudge if the user hasn't completed onboarding

### TABLE: email_logs
```
id UUID PK DEFAULT gen_random_uuid()
user_id UUID references profiles(id)
email_type TEXT NOT NULL
status TEXT DEFAULT 'sent'
sent_at TIMESTAMPTZ DEFAULT now()
```

---

## EDGE CASES
- Quiz mode with no questions returned: fall back to normal explanation + note
- Streak across timezones: use the user's local date (store timezone in profile or compute client-side)
- Onboarding back navigation preserves selections
- Email reminders: never send if email consent is false or user asked today

---

## SECURITY REQUIREMENTS
- quiz_attempts and progress data RLS-scoped to the user
- A/B exposure only after analytics consent
- Resend API key in Edge Function secrets only
- Email reminders respect consent and unsubscribe

---

## SUCCESS CRITERIA
- Onboarding sets curriculum/class/subject and routes to chat with those defaults
- Quiz mode renders interactive MCQs with feedback, scoring, and citations
- Streak counter increments daily and shows on the sidebar
- Mobile layout works at 375px — sidebar collapses, input reachable
- SEO metadata present; bilingual lang attribute switches
- Upgrade CTA A/B variants assigned consistently per user
- Streak reminder email sends to eligible, consented users
