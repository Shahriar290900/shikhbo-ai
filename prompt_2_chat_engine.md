# SHIKHBO — LOVABLE PROMPT 2: THE CHAT ENGINE
## CRUD · Chat State · Voice · Streaming UI

---

## CONTEXT
Building on the Shikhbo foundation from Prompt 1 (auth, schema, app shell). This prompt makes the chat fully functional: sending and persisting messages, conversation history, the subject/mode/quality state flowing into each request, voice input, text-to-speech playback, and the sources display. The actual AI call is proxied through an Edge Function (the real Hugging Face connection is wired in Prompt 3 — here, build the Edge Function with a clean placeholder response so the full UI flow works end to end).

## OBJECTIVE
Implement full chat CRUD with session management, real-time message rendering, voice-to-text input via the Web Speech API, text-to-speech playback of answers, the expandable sources panel, and a Supabase Edge Function `ask-shikhbo` that currently returns a structured placeholder (to be connected to HF in Prompt 3).

---

## CHAT FUNCTIONALITY

### Sending a message
On send:
1. If no active session, create a chat_sessions row (title = first 40 chars of the query, subject/curriculum/class from current selection + profile)
2. INSERT user message into messages (role='user', content, mode, quality, subject)
3. Optimistically render the user message immediately
4. Show an assistant "typing…" indicator (animated dots)
5. Call Edge Function `ask-shikhbo` with { query, subject, curriculum, class_level, mode, quality, session_id }
6. INSERT the returned assistant message (role='assistant', content, sources, grounded flag, model info)
7. Render the assistant message with sources panel and TTS button
8. On error: show a retry option, keep the user message

### Conversation history
- Left sidebar (below the selectors, or a separate history drawer): list of past chat_sessions for the user, ordered by updated_at desc, showing title + relative time
- Clicking a session loads its messages into the chat area
- "New Chat" button clears the active session
- Each session row: rename and delete actions (delete cascades messages)

### Messages query
Use TanStack Query: key ['messages', sessionId], staleTime 30s. Invalidate after each send.

---

## EDGE FUNCTION: ask-shikhbo (placeholder version)

Create Supabase Edge Function `ask-shikhbo`:
- Auth: verify JWT, reject if no user
- Input: { query, subject, curriculum, class_level, mode, quality, session_id }
- Validate: query non-empty (max 1000 chars), subject in allowed list, mode in allowed list
- For now, RETURN a structured placeholder:
```json
{
  "answer": "[Placeholder] You asked about: {query}. The AI backend will answer here in {mode} mode for {subject}.",
  "sources": [],
  "grounded": false,
  "model_used": "placeholder"
}
```
- Increment usage_tracking for the user (message_count++) for today's date (UPSERT)
- This function's response shape MUST match what Prompt 3 will replace it with, so the UI never changes.

---

## MODE BEHAVIOR (pass to Edge Function, shapes the future AI prompt)
- **Normal:** standard grounded answer
- **Simple:** simplified, concept-building explanation for a struggling student
- **Quiz:** generate self-assessment questions from the topic instead of a direct answer
- **Step-by-Step:** structured solution (especially Physics calculations: formula → substitution → units → answer)

The mode + quality + subject + curriculum + class travel with every request. Render the active selection as the small tag row above the input (e.g. "ICT · NORMAL · FAST · SSC · NATIONAL").

---

## VOICE INPUT (Speech-to-Text)
- Microphone button in the input bar
- Use the browser Web Speech API (webkitSpeechRecognition / SpeechRecognition)
- Set recognition language based on ui_language: 'bn-BD' for Bengali, 'en-US' for English
- While listening: mic button pulses red, show "Listening…" placeholder
- On result: populate the text input with the transcript; user can edit before sending
- On unsupported browser: hide the mic button gracefully, show tooltip "Voice input not supported in this browser"
- Increment usage_tracking.voice_count on use

## TEXT-TO-SPEECH (answer playback)
- Speaker icon on each assistant message
- Use the browser SpeechSynthesis API
- Select voice by language: Bengali (bn) voice if available, else fall back to default with a note
- Clicking: play/stop toggle, highlight while speaking
- Note: high-quality Bengali TTS is a premium feature (Prompt 4 gates the cloud TTS); this browser TTS is the free-tier baseline

---

## SOURCES PANEL
- Each grounded assistant message shows "Sources ▼"
- Expanded: list each source as a card — chapter title, page number, chunk_id (small/muted)
- If grounded=false: show a subtle badge "General explanation — not from your textbook" instead of sources, matching the fallback behavior
- This is the trust mechanism — make it visually clear which answers are textbook-grounded

---

## EDGE CASES & VALIDATION
- Empty query: disable send button
- Query over 1000 chars: show counter, block send
- Session deleted while open: redirect to /chat (new session)
- Voice not supported: hide mic, no crash
- TTS not supported: hide speaker icon
- Network error on send: show "Failed to send — Retry" without losing the typed message
- Rapid double-send: disable send button while a request is in flight

---

## SECURITY REQUIREMENTS
- ask-shikhbo verifies JWT before processing
- Message content is rendered as plain text (no HTML injection)
- Users can only load sessions where user_id = auth.uid() (enforced by RLS)
- File attachment handling deferred to Prompt 3, but the attach button can upload to chat-uploads bucket under {user_id}/ path now

---

## SUCCESS CRITERIA
- User can send a message and see it persist + reload on refresh
- Conversation history lists past sessions and loads them
- Subject/Mode/Quality selections flow into the Edge Function call and appear as tags
- Voice input transcribes into the text box (in supporting browsers)
- TTS reads assistant answers aloud
- Sources panel expands; grounded vs general-fallback states render differently
- ask-shikhbo returns the placeholder in the exact response shape Prompt 3 will use
