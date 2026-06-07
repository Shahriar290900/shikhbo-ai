# SHIKHBO — LOVABLE PROMPT 3: AI INTEGRATION & SCALE
## Connect Hugging Face · Vision/OCR · Rate Limiting · Caching

---

## CONTEXT
Building on Shikhbo Prompts 1–2 (auth, schema, working chat with placeholder Edge Function). This prompt connects the real AI: the `ask-shikhbo` Edge Function now calls the external Hugging Face Spaces RAG API; premium image upload calls the HF vision endpoint; and the system gets rate limiting, response caching, and streaming. The HF backend is deployed separately and exposes the API contract below.

## OBJECTIVE
Rewire `ask-shikhbo` to call the Hugging Face `/chat` API, add an `analyze-image` Edge Function calling the HF `/vision` endpoint for premium users, implement per-user/per-tier rate limiting, cache identical recent queries, and stream the answer into the UI.

---

## HUGGING FACE API CONTRACT (external backend, already deployed)

The HF Space base URL and access token are stored as Supabase secrets: `HF_API_URL`, `HF_API_TOKEN`. Never expose these to the client.

```
POST {HF_API_URL}/chat
Headers: Authorization: Bearer {HF_API_TOKEN}
Body: { query, subject, curriculum, class_level, mode, quality }
Returns: {
  answer: string,
  sources: [{ chunk_id, chapter, page }],
  grounded: boolean,
  model_used: string
}

POST {HF_API_URL}/vision     (premium only)
Body: { image_base64, query, subject, curriculum }
Returns: { extracted_text, answer, sources, grounded }
```

---

## REWIRE ask-shikhbo (replace placeholder)

Update the Edge Function to:
1. Verify JWT, get user_id
2. Read the user's tier from profiles
3. **Rate limit check** (see below) — return 429 if exceeded
4. **Cache check**: hash (query + subject + mode + curriculum) into a cache key; look up a `response_cache` table; if a fresh (< 24h) entry exists, return it without calling HF (saves cost + latency)
5. If `quality='enhanced'` but tier='free': downgrade to 'fast' and include a flag `quality_downgraded: true` so the UI can prompt upgrade
6. Call `{HF_API_URL}/chat` with the request body, Authorization header from secret
7. On HF success: INSERT assistant message, store in response_cache, increment usage_tracking, return answer + sources
8. On HF timeout (> 30s) or error: return a graceful message "AI is busy, please try again" with status indicating retry; do NOT crash
9. Stream the response to the UI if the HF endpoint supports streaming (otherwise return complete)

### TABLE: response_cache
```
id: UUID PRIMARY KEY DEFAULT gen_random_uuid()
cache_key: TEXT UNIQUE NOT NULL          -- sha256(query|subject|mode|curriculum)
subject: TEXT
answer: TEXT NOT NULL
sources: JSONB DEFAULT '[]'
grounded: BOOLEAN
created_at: TIMESTAMPTZ DEFAULT now()
```
INDEX: response_cache_key_idx ON response_cache(cache_key)
No user-specific RLS (cache is shared, non-personal) — but only Edge Functions (service role) write to it.

---

## VISION / OCR — analyze-image Edge Function (premium only)

Create Edge Function `analyze-image`:
1. Verify JWT, get user_id and tier
2. **If tier != 'premium': return 403** with message "Image analysis is a premium feature" (UI shows upgrade prompt)
3. Rate limit: premium users max 20 image analyses per day
4. Input: { image_path } (path in chat-uploads bucket) + { query, subject }
5. Download the image from Supabase Storage, convert to base64
6. Call `{HF_API_URL}/vision` with image_base64 + query + subject + curriculum
7. Return { extracted_text, answer, sources, grounded }
8. Increment usage_tracking.image_count
9. Store the result as an assistant message with has_attachment=true

### Frontend wiring
- The paperclip/attach button: free users see a lock badge + "Premium" tooltip; clicking opens upgrade modal
- Premium users: file picker (image/pdf, max 10MB), upload to chat-uploads/{user_id}/, then call analyze-image
- Show image thumbnail in the chat, then the extracted text + answer below it

---

## RATE LIMITING

Implement in the Edge Functions using a `rate_limits` table (Supabase-native, no external Redis needed for this scale):

### TABLE: rate_limits
```
user_id: UUID NOT NULL
window_start: TIMESTAMPTZ NOT NULL
request_count: INTEGER DEFAULT 1
endpoint: TEXT NOT NULL
PRIMARY KEY (user_id, endpoint, window_start)
```

Limits by tier (sliding window, per day unless noted):
```
                      Free        Premium
Chat messages         30/day      unlimited
Voice input           20/day      unlimited
Image analysis        0 (locked)  20/day
Messages per minute   5           20
```
On limit exceeded: return 429 with { error, retry_after, upgrade_prompt: true }. The UI shows "You've reached today's free limit — upgrade for unlimited" with an upgrade button.

---

## CACHING & PERFORMANCE
- Response cache (above): identical questions return instantly, saving HF compute
- TanStack Query staleTime: messages 30s, sessions 2min, subjects/static config 1h
- Lazy-load conversation history (paginate sessions, 20 at a time)
- Show skeleton loaders while messages load
- Debounce the chat input's character counter

---

## EDGE CASES & VALIDATION
- HF Space cold start (first request slow / 503): retry once after 3s, then show "AI is waking up, try again in a moment"
- HF returns malformed JSON: catch, return graceful error, log to console
- Free user hits message limit mid-conversation: block with upgrade prompt, don't lose context
- Image upload of unsupported type: client-side reject before upload
- Image over 10MB: reject with clear message
- Enhanced quality requested by free user: silently use fast + flag for upgrade nudge
- Cache key collision across curricula: include curriculum in the hash (an ICT and Physics question with same words must not collide)

---

## SECURITY REQUIREMENTS
- HF_API_URL and HF_API_TOKEN stored as Supabase secrets, used only server-side in Edge Functions — NEVER in client code or returned to client
- analyze-image enforces premium tier server-side (not just hidden in UI)
- Rate limiting enforced in Edge Function, not client
- Image files: validate MIME server-side before sending to HF
- Cache table writable only by service role (Edge Functions), readable by Edge Functions only

---

## SUCCESS CRITERIA
- Real Bengali/English answers from the HF backend appear in chat with correct sources
- Mode (normal/simple/quiz/step-by-step) visibly changes the answer style
- Premium image upload extracts text and answers; free users see the upgrade gate
- Free user is blocked at 30 messages/day with an upgrade prompt
- Identical repeated question returns from cache (visibly faster, no HF call)
- HF cold start / error shows a graceful retry message, never a crash
- HF token is never visible in the browser network tab or client bundle
