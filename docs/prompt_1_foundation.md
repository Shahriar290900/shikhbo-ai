# SHIKHBO — LOVABLE PROMPT 1: THE FOUNDATION
## Plan Mode · Schema · Auth (incl. Google) · App Shell

---

## CONTEXT
Build the foundation for "Shikhbo" (শিখবো) — a bilingual (Bengali/English) AI study assistant for Bangladeshi students following the NCTB curriculum (SSC ICT) and Edexcel International A-Level (Physics). The AI inference runs on an external Hugging Face API (built separately) — this app calls it later. This prompt builds the database, authentication including Google sign-in, and the full UI shell.

## OBJECTIVE
Create the complete Supabase database schema, authentication with email/password AND Google OAuth, role-aware routing, and the application shell (login page + chat layout) matching the Shikhbo design, using React, shadcn/ui, TanStack Query, and Tailwind.

---

## DATABASE SCHEMA (Supabase / PostgreSQL)

### TABLE: profiles
```
id: UUID PRIMARY KEY references auth.users(id) ON DELETE CASCADE
email: TEXT NOT NULL
full_name: TEXT
avatar_url: TEXT
ui_language: TEXT DEFAULT 'bn' CHECK (ui_language IN ('bn','en'))
curriculum: TEXT DEFAULT 'NCTB' CHECK (curriculum IN ('NCTB','Edexcel_IAL'))
class_level: TEXT DEFAULT 'SSC' CHECK (class_level IN ('SSC','HSC','A-level'))
default_subject: TEXT DEFAULT 'ICT' CHECK (default_subject IN ('ICT','Bangla','Physics'))
tier: TEXT DEFAULT 'free' CHECK (tier IN ('free','premium'))
onboarding_complete: BOOLEAN DEFAULT FALSE
created_at: TIMESTAMPTZ DEFAULT now()
updated_at: TIMESTAMPTZ DEFAULT now()
```
RLS: users read/write only their own row.

### TABLE: chat_sessions
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id: UUID NOT NULL references profiles(id) ON DELETE CASCADE
title: TEXT
subject: TEXT NOT NULL CHECK (subject IN ('ICT','Bangla','Physics'))
curriculum: TEXT NOT NULL
class_level: TEXT NOT NULL
created_at: TIMESTAMPTZ DEFAULT now()
updated_at: TIMESTAMPTZ DEFAULT now()
```
INDEX: chat_sessions_user_idx ON chat_sessions(user_id, updated_at DESC)
RLS: users access only their own sessions.

### TABLE: messages
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
session_id: UUID NOT NULL references chat_sessions(id) ON DELETE CASCADE
user_id: UUID NOT NULL references profiles(id)
role: TEXT NOT NULL CHECK (role IN ('user','assistant'))
content: TEXT NOT NULL
mode: TEXT CHECK (mode IN ('normal','simple','quiz','step_by_step'))
quality: TEXT CHECK (quality IN ('fast','enhanced'))
subject: TEXT
sources: JSONB DEFAULT '[]'          -- array of {chunk_id, chapter, page}
grounded: BOOLEAN                     -- true if answered from textbook, false if general fallback
has_attachment: BOOLEAN DEFAULT FALSE
attachment_path: TEXT
created_at: TIMESTAMPTZ DEFAULT now()
```
INDEX: messages_session_idx ON messages(session_id, created_at)
RLS: users access only messages in their own sessions.

### TABLE: subscriptions
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id: UUID NOT NULL UNIQUE references profiles(id) ON DELETE CASCADE
stripe_customer_id: TEXT UNIQUE
stripe_subscription_id: TEXT UNIQUE
plan: TEXT DEFAULT 'free' CHECK (plan IN ('free','premium'))
status: TEXT DEFAULT 'active' CHECK (status IN ('trialing','active','past_due','canceled'))
current_period_end: TIMESTAMPTZ
created_at: TIMESTAMPTZ DEFAULT now()
updated_at: TIMESTAMPTZ DEFAULT now()
```
RLS: users read only their own; admins read all.

### TABLE: usage_tracking
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id: UUID NOT NULL references profiles(id) ON DELETE CASCADE
usage_date: DATE NOT NULL DEFAULT CURRENT_DATE
message_count: INTEGER DEFAULT 0
voice_count: INTEGER DEFAULT 0
image_count: INTEGER DEFAULT 0
UNIQUE (user_id, usage_date)
```
RLS: users read their own; system updates via Edge Function.

### TABLE: user_consents
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id: UUID NOT NULL references profiles(id) ON DELETE CASCADE
consent_type: TEXT NOT NULL CHECK (consent_type IN ('terms','privacy','analytics','cookies'))
consented: BOOLEAN NOT NULL
version: TEXT NOT NULL
consented_at: TIMESTAMPTZ DEFAULT now()
```
RLS: users manage only their own.

---

## AUTHENTICATION

Configure Supabase Auth with:
- Email + Password provider
- **Google OAuth provider** (enabled)

Create trigger `on_auth_user_created`: after INSERT on auth.users, INSERT into profiles(id, email, full_name, avatar_url) using new.id, new.email, new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'avatar_url'. This works for both email signup and Google (Google provides name + avatar automatically).

Create `update_updated_at` trigger BEFORE UPDATE on all tables.

After login: read profiles.onboarding_complete. If false → /onboarding. If true → /chat.

---

## APPLICATION SHELL

### Routes (React Router v6)
```
/ — public landing (the "Learn smarter, not harder" hero + Log In / Sign Up card)
/auth/callback — OAuth redirect handler
/onboarding — set curriculum, class, default subject (protected)
/chat — main chat interface (protected)
/chat/:sessionId — specific conversation
/settings — profile + billing + privacy
/admin — admin only
```

### Landing / Auth Page (match the prototype)
- Left: bold hero text "Learn smarter, not harder." + tagline "Tough topics, now in your pocket. Study made easy, step by step, your way." + "YOUR AI STUDY PARTNER" pill badge. Dark background with subtle grid pattern.
- Right: card with "Log In" / "Sign Up" tabs. Email + Password fields. White "Log In" button. Below: "No account? Sign up".
- **A "Continue with Google" button** with the Google logo, above or below the email form, on both Log In and Sign Up tabs.
- Top-right: বাংলা / English language toggle.
- Logo top-left: "◯ শিখবো - Shikhbo".

### Chat Layout (match the prototype)
Top bar: "◯ শিখবো - Shikhbo" logo · "Edit Profile" link · বাংলা/English toggle · Dark/Light toggle · "Log Out".

Left sidebar (collapsible on mobile):
- **SUBJECT** section: three selectable pills — ICT, Bangla, Physics (single select, highlights selected)
- **RESPONSE QUALITY** section: Fast / Enhanced (single select)
- **MODE** section: Normal / Simple / Quiz / Step-by-Step (single select)

Main chat area:
- Message list: user messages right-aligned in a bubble, assistant messages left-aligned with a circular avatar. Assistant messages show a speaker icon (TTS playback) and a "Sources ▼" expandable dropdown.
- Empty state when no messages: friendly prompt to ask a question.

Bottom input bar:
- Attach file icon (paperclip)
- Text input "Ask a question…"
- Microphone icon (voice input)
- Send button
- Above the input: small context tags showing current selection, e.g. ICT · NORMAL · FAST · SSC · NATIONAL

Build all selectors as controlled state (useState) — wire the actual send logic in Prompt 2. For now the send button can store the message in the DB and show a placeholder assistant reply.

---

## SECURITY REQUIREMENTS
- Enable RLS on ALL tables
- Create helper `auth.user_tier()` returning the user's tier from profiles
- Protected routes check session on mount, redirect to / if none
- VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY as env vars only
- Create Supabase Storage bucket `chat-uploads` (private, 10MB limit, image/jpeg, image/png, image/webp, application/pdf), RLS so users access only files under their own user_id folder

---

## SUCCESS CRITERIA
- All 6 tables created with constraints, indexes, RLS
- Email signup AND Google sign-in both work and create a profile row
- Landing page matches the hero + auth card design
- Chat layout renders with working Subject / Quality / Mode selectors
- Language toggle (বাংলা/English) and Dark/Light toggle function
- Protected routes redirect unauthenticated users to landing
