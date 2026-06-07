# Shikhbo — Beginner's Guide to Connectors
## How to connect Lovable to everything it needs (written for a first-timer)

A "connector" (or integration) is how your Lovable app talks to another service. Shikhbo needs four connections. Do them in this order. Each one is mostly clicking buttons and copy-pasting keys — no coding.

---

## CONNECTION 1 — Lovable ↔ Supabase (database + auth)
**What it does:** Gives your app its database, user accounts, file storage, and Edge Functions.

**Steps:**
1. In your Lovable project, look for the **Supabase** button (top right, or in the integrations/settings panel).
2. Click **"Connect Supabase."**
3. A window opens asking you to log in to Supabase (create a free account at supabase.com if you don't have one — use Google to sign up, it's fastest).
4. Click **"Authorize"** to let Lovable connect.
5. Choose **"Create a new Supabase project"** (or select an existing one). Give it a name like `shikhbo`. Pick a region close to Bangladesh (Singapore is closest). Set a database password and **save it somewhere safe**.
6. Wait ~2 minutes for the project to provision.
7. Back in Lovable, it will confirm "Supabase connected." Done.

**You never touch the database password again unless self-hosting.** Lovable wires the URL and keys automatically.

---

## CONNECTION 2 — Google Sign-In (via Supabase)
**What it does:** Lets students log in with their Google account (the "Continue with Google" button).

This is set up in **Supabase**, not Lovable directly. You need a Google Cloud "OAuth Client."

**Part A — Get Google credentials:**
1. Go to **console.cloud.google.com** and sign in with your Google account.
2. Top bar → **Create Project** → name it `Shikhbo` → Create.
3. Left menu → **APIs & Services** → **OAuth consent screen**.
   - User type: **External** → Create.
   - App name: `Shikhbo`. User support email: your email. Developer email: your email. Save and continue through the screens (you can skip scopes for now). Add yourself as a **Test user**.
4. Left menu → **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**.
   - Application type: **Web application**.
   - Name: `Shikhbo Web`.
   - Under **Authorized redirect URIs**, click Add URI. You need your Supabase callback URL — get it in the next step, then come back.

**Part B — Get the Supabase callback URL:**
1. In Supabase dashboard → your project → **Authentication** → **Providers** → **Google**.
2. Copy the **Redirect URL** shown there (looks like `https://YOURPROJECT.supabase.co/auth/v1/callback`).
3. Paste it into the Google "Authorized redirect URIs" field from Part A → **Create**.
4. Google shows a **Client ID** and **Client Secret** — copy both.

**Part C — Connect them:**
1. Back in Supabase → Authentication → Providers → **Google** → toggle **Enabled**.
2. Paste the **Client ID** and **Client Secret**. **Save.**

Now the "Continue with Google" button in your app works. Test it after Prompt 1 builds.

---

## CONNECTION 3 — Stripe (subscription payments)
**What it does:** Handles the Premium upgrade payments.

**Steps:**
1. Create a free account at **stripe.com**. Stay in **Test mode** (toggle top-right) while building.
2. In Stripe dashboard → **Products** → **Add product**:
   - Name: `Shikhbo Premium`. Price: e.g. `$2.00` (or ৳200) **recurring monthly**. Save.
   - Copy the **Price ID** (looks like `price_xxxxx`) — you'll give this to Lovable.
3. In Stripe → **Developers** → **API keys**: copy the **Secret key** (`sk_test_xxx`) and **Publishable key** (`pk_test_xxx`).
4. In Lovable, when Prompt 4 runs, it will ask for Stripe keys, OR you add them as **Supabase secrets**:
   - Supabase dashboard → **Project Settings** → **Edge Functions** → **Secrets** (or **Vault**) → add:
     - `STRIPE_SECRET_KEY` = your `sk_test_xxx`
     - `STRIPE_PRICE_PREMIUM` = your `price_xxxxx`
5. **Webhook** (Prompt 4 creates the endpoint): in Stripe → Developers → Webhooks → Add endpoint → paste your Supabase Edge Function URL for `stripe-webhook` → select events `customer.subscription.*` and `invoice.*` → copy the **Signing secret** (`whsec_xxx`) → add as Supabase secret `STRIPE_WEBHOOK_SECRET`.

When you go live later, swap test keys for live keys.

---

## CONNECTION 4 — Your Hugging Face AI Backend (the brain)
**What it does:** This is where your RAG + LLM actually answers questions. Lovable's Edge Function calls it.

**Steps:**
1. Deploy your Shikhbo Python RAG code as a **Hugging Face Space** (separate from Lovable):
   - Go to **huggingface.co** → create a free account.
   - Click your profile → **New Space**.
   - Name: `shikhbo-ai`. License: pick one. SDK: **Docker** (or Gradio if you wrap it that way). Hardware: start with **CPU basic (free)**; upgrade to a GPU for the demo.
   - Upload your Python code (the RAG pipeline that exposes the `/chat` and `/vision` endpoints from the architecture doc).
2. Once the Space is running, your API URL is `https://YOURNAME-shikhbo-ai.hf.space`.
3. Create an **access token**: HF → Settings → **Access Tokens** → New token (read) → copy it.
4. Add these as **Supabase secrets** (so Edge Functions can reach the AI):
   - `HF_API_URL` = `https://YOURNAME-shikhbo-ai.hf.space`
   - `HF_API_TOKEN` = your HF token
5. Prompt 3's `ask-shikhbo` Edge Function reads these secrets and calls your AI. You never put them in the frontend.

**For the demo ($10 budget):** upgrade the Space hardware to a small GPU (T4) only on demo days, then set it back to CPU/sleep to stop billing.

---

## WHERE EACH SECRET LIVES (cheat sheet)
| Secret | Where to store it | Who uses it |
|---|---|---|
| Supabase URL + anon key | Auto-set by Lovable | Frontend (safe) |
| Google Client ID + Secret | Supabase → Auth → Google | Supabase auth |
| STRIPE_SECRET_KEY | Supabase Edge Function secrets | Edge Functions only |
| STRIPE_WEBHOOK_SECRET | Supabase Edge Function secrets | Webhook function |
| STRIPE_PRICE_PREMIUM | Supabase Edge Function secrets | Checkout function |
| HF_API_URL + HF_API_TOKEN | Supabase Edge Function secrets | ask-shikhbo / analyze-image |

**Golden rule:** Secret keys (anything starting with `sk_`, `whsec_`, or your HF token) go in **Supabase secrets**, NEVER in the frontend or in a prompt. Publishable keys (`pk_`) and the Supabase anon key are safe in the frontend.

---

## ORDER OF OPERATIONS (when to connect what)
1. **Before Prompt 1:** Connect Supabase (Connection 1)
2. **After Prompt 1 builds:** Set up Google sign-in (Connection 2), test the login
3. **Before Prompt 3:** Deploy the HF Space + add HF secrets (Connection 4)
4. **Before Prompt 4:** Set up Stripe + add Stripe secrets (Connection 3)
5. **After Prompt 5:** Run the free Security Check, then Publish
