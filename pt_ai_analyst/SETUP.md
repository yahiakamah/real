# SETUP — PomoTech AI Analyst (`pt_ai_analyst`)

Complete, step-by-step guide to install, configure and run the module, including
every other program that must be prepared. Follow the sections in order. Time:
~20–30 minutes for a first run.

---

## 0. What needs to be prepared (at a glance)

| Component | Needed for | Required? |
|-----------|-----------|-----------|
| Odoo 18 + PostgreSQL | The module itself | **Required** |
| Python `requests` | Calling the AI provider | **Required** |
| Python `python-dateutil` | Relative dates / period comparison | **Required** (ships with Odoo) |
| A Gemini API key | The AI brain | **Required** |
| Python `xlsxwriter` | Excel (.xlsx) export | Optional |
| `wkhtmltopdf` (Odoo build) | PDF export | Optional |
| Chrome/Edge + HTTPS + mic | Voice (talk & spoken replies) | Optional |
| HeyGen account/key | Realtime video avatar (optional mode) | Optional |

The module installs and runs with only the **Required** rows. The optional rows
each degrade to a friendly message if missing — they never block anything else.

---

## 1. Server prerequisites

- **Odoo 18.0** (Community or Enterprise) already installed and running.
- **PostgreSQL** (whatever your Odoo already uses).
- **Python 3.10+** (the interpreter your Odoo runs on).

Confirm Odoo starts normally before adding this module.

---

## 2. Python libraries

Install into the **same Python environment Odoo uses** (venv, system, or the
user Odoo runs as). Example:

```bash
# required
pip install requests
# optional – Excel export
pip install xlsxwriter
```

- `python-dateutil` is already a hard dependency of Odoo, so it's normally
  present. If a fresh venv complains, `pip install python-dateutil`.
- `requests` is listed in the manifest's `external_dependencies`; Odoo will
  refuse to install the module until it's importable.

### wkhtmltopdf (only if you want PDF export)

PDF export uses Odoo's standard QWeb→PDF pipeline, which needs the
**Odoo-recommended patched wkhtmltopdf 0.12.6** (the distro package often can't
render headers/footers). Get it from the wkhtmltopdf releases page for your OS,
install it, and make sure `wkhtmltopdf` is on the PATH of the Odoo process. Test:

```bash
wkhtmltopdf --version   # should print 0.12.6 (with patched qt)
```

If wkhtmltopdf is absent, CSV and Excel export still work; only PDF shows a
"PDF export is unavailable on this server" message.

---

## 3. Install the module

1. Copy the `pt_ai_analyst` folder into one of your Odoo **addons paths**
   (the folders listed in `addons_path` in your Odoo config).
2. Restart the Odoo service.
3. In Odoo: turn on **Developer Mode** (Settings → scroll down → Activate
   developer tools).
4. **Apps → Update Apps List** (top menu, dev mode only) → confirm.
5. Search **"PomoTech AI Analyst"** → **Install**.

If install fails complaining about `requests`, finish section 2 first.

---

## 4. Give yourself access (security groups)

The module ships three groups. Assign them per user:

- **AI Analyst / User** — can chat with the assistant over data they're already
  allowed to see.
- **AI Analyst / Manager** — the above, plus see all conversations and the audit log.
- **AI Analyst / Administrator** — the above, plus configure providers, the
  semantic layer and suggested questions.

Go to **Settings → Users & Companies → Users → (your user) → Access Rights**,
find the **AI Analyst** category, pick **Administrator** for yourself, save.
Log out/in if the menu doesn't appear immediately.

---

## 5. Configure the Gemini provider (the AI brain)

### 5.1 Get a Gemini API key
1. Open **Google AI Studio** (aistudio.google.com) and sign in.
2. **Get API key → Create API key**. Copy it (starts with `AIza...`).
3. Make sure billing/quota is enabled for the model you'll use.

### 5.2 Point the module at it
**AI Analyst → Configuration → Providers → "Default Provider"** and set:

- **Provider**: `Google Gemini (generateContent)`
- **Model**: a **current** model your key supports. As of now:
  - `gemini-3.6-flash` — current recommended flash model (the shipped default).
  - `gemini-3.5-flash` / `gemini-3.7-flash` — newer options.
  - ⚠️ `gemini-2.5-pro` is scheduled to shut down **16 Oct 2026** — avoid it.
  - Model names change over time; the authoritative list is Google's Gemini API
    changelog/models page. Use whatever is current for your key.
- **API Base URL**: leave **empty** (defaults to
  `https://generativelanguage.googleapis.com/v1beta`).
- **API Key**: paste your `AIza...` key.
- **Temperature**: `0.0` (best for accurate, non-creative analytics).
- **Max Tokens**: `1024`–`2048`.
- Save.

> The key is stored server-side only and is never sent to the browser or written
> into conversation/audit logs.

### Using Anthropic or an OpenAI-compatible endpoint instead
Change **Provider** to Anthropic or OpenAI-compatible, set the matching **Model**
and **API Key**, and (for self-hosted gateways) the **API Base URL**. Everything
else works the same.

---

## 6. Configure the Semantic Layer (what the AI may analyse)

This is the most important step. The AI can **only** touch models and fields you
register here, and only rows the logged-in user is already permitted to read.
**No model names are hard-coded** — you decide.

For **each** business model you want the assistant to reason over:

1. **AI Analyst → Configuration → Semantic Layer → New**.
2. **Odoo Model**: pick the model (e.g. your analysis/order/invoice model).
3. **Business Name** + **Business Meaning**: describe it in plain language
   (this text is what the AI reads to understand the data).
4. **Primary Date Field**: the field used for date filters and period comparison
   (e.g. `create_date`, `date_order`, `request_date`). Required for
   "this month vs last", trends and "why did X change?".
5. **Base Domain** (optional): a Python domain always applied, e.g.
   `[('state','!=','cancel')]`.
6. Click **Discover Fields** — it reads the model's real fields and guesses which
   are **measures** (numbers you can sum/avg) and **dimensions** (things you can
   group/filter by).
7. Review the **Fields** tab and tick correctly:
   - **Visible to AI** — uncheck anything the AI shouldn't see at all.
   - **Measure** — numeric fields to aggregate (amount, quantity, duration…).
   - **Dimension** — fields to group/filter (branch, type, status, date…).
   - **Sensitive** — personal/medical/financial fields to keep minimally exposed.
8. Save.

> Tip: start with 1–2 core models (e.g. the analysis records and the invoice/
> revenue model), verify answers, then add more (branches, departments, …).

---

## 7. Suggested questions (optional polish)

**AI Analyst → Configuration → Suggested Questions** ships a few Arabic starters.
Edit/add your own, and optionally set a **Required Group** so a suggestion only
shows to users who can run it.

---

## 8. Avatar (browser animated vs HeyGen video)

The avatar mode is set in **AI Analyst → Configuration → Avatar**:

- **In-browser animated avatar (default, free):** an animated on-screen face that
  blinks and **lip-syncs while speaking**, driven by the browser voice. No account,
  no cost — works immediately.
- **HeyGen realtime video avatar:** a realistic streaming video avatar. Set it up:
  1. Create a HeyGen account and get an **API key** (and pick a **Streaming
     Avatar** to get its **Avatar ID**).
  2. In **Configuration → Avatar**, choose *HeyGen*, paste the **API Key** and
     **Avatar ID**, set quality, save.
  3. The key stays on the server; the browser only gets a short-lived session
     token. The HeyGen streaming SDK is loaded at runtime — the deployment needs
     outbound network access to HeyGen (and possibly its domains allowed in your
     Content-Security-Policy). If the video avatar can't start, the module falls
     back to the animated avatar automatically.
  4. In HeyGen mode the avatar speaks the answers, so the browser voice toggle is
     hidden.

> HeyGen is a paid third-party service and needs live testing with your own key.

## 8b. Voice requirements (talk to the avatar)
Voice uses the browser's built-in **Web Speech API** — no server keys, nothing to
install on the server. For it to work in the client:

- **Browser**: Google **Chrome** or **Microsoft Edge** (best support for both
  speech-to-text and text-to-speech). Firefox supports spoken replies but limited
  microphone recognition; Safari is partial.
- **Secure context**: the page must be served over **HTTPS** (or `localhost`).
  Microphone speech recognition is blocked on plain `http://` origins.
- **Microphone permission**: the browser will prompt on first mic use — allow it.
- **Arabic/English voices**: spoken replies use the voices installed on the
  **user's operating system**. If no Arabic voice is installed, Windows/macOS can
  add one via their language/speech settings; otherwise replies fall back to a
  default voice.

In the assistant: the **microphone** button (speak), the **Voice** chip (turn
spoken replies on/off), and the **ع / EN** chip (speech-input language) appear
only when the browser supports them. The reply is spoken in the **same language**
the answer is written in (auto-detected).

---

## 8c. Arabic voice on Linux / Ubuntu

Linux browsers usually ship **no Arabic voice**, so spoken replies stay silent
even though everything else works. Two fixes:

**Quick / free (robotic):**

```bash
sudo apt update && sudo apt install -y speech-dispatcher espeak-ng
```

Then use **Firefox** (it speaks via speech-dispatcher/espeak). You'll get an
Arabic voice — functional but robotic — enough to validate the hands-free loop.

**Recommended / natural (server voice):** in **Configuration → Avatar → Voice**
set **Voice = Server / cloud voice**, provider **Google Cloud Text-to-Speech**,
paste a **TTS API key**, and optionally set the Arabic/English voice names
(defaults: `ar-XA-Wavenet-B`, `en-US-Wavenet-D`). Enable the *Cloud Text-to-Speech
API* on your Google project — you can often reuse your Gemini key if it isn't
API-restricted. The server synthesizes natural audio and the page plays it, so it
works on any OS regardless of installed voices. (Azure and ElevenLabs, which have
native Egyptian-Arabic voices, can be added later behind the same setting.)

## 9. Final verification checklist (test everything at once)

Open **AI Analyst → Assistant** and run through:

1. **Basic**: "How many records this month?" → a number, no error.
2. **Aggregation/ranking**: "Top 10 by count" → a table or bar chart.
3. **Comparison**: "Compare this month with last month" → deltas + %.
4. **Explainability**: "Why did revenue change this month?" → decomposition by a
   dimension (biggest movers).
5. **Dashboard**: "Give me a management summary" → several KPIs/charts in a grid.
6. **Visuals**: confirm KPI/table/bar/line/pie render inline.
7. **Export**: on an answer with data, click **CSV**, **Excel**, **PDF** and open
   each file (Excel needs xlsxwriter; PDF needs wkhtmltopdf).
8. **Voice**: click the mic, ask in Arabic → it transcribes, answers, and speaks
   back in Arabic; repeat in English.
9. **Conversation management**: rename a conversation, search the list, delete one.
10. **Security**: log in as a **limited user** (no financial access) and confirm a
    revenue question returns "no access / not available" rather than numbers.
11. **Multi-company** (if used): confirm answers respect the active company.

---

## 10. Troubleshooting

- **"No AI provider is configured" / "no API key"** → section 5.2.
- **Model 404 / "AI service returned an error"** → the model name isn't valid for
  your key; pick a current one (section 5.2) and check quota/billing.
- **"This information is not available to the assistant"** → the model/field isn't
  enabled in the Semantic Layer (section 6), or the user lacks Odoo read access.
- **"can't be compared over time"** → set the **Primary Date Field** on that
  semantic model.
- **Excel button shows a text message** → `pip install xlsxwriter`, restart Odoo.
- **PDF button shows a text message** → install the Odoo-recommended wkhtmltopdf
  (section 2), ensure it's on the Odoo process PATH.
- **Mic button missing / speech doesn't start** → use Chrome/Edge over HTTPS and
  allow the microphone.
- **Replies aren't spoken / wrong voice** → enable the **Voice** chip; install an
  Arabic system voice for Arabic replies.

---

## 11. What's implemented vs. optional

Both avatar modes are **implemented**: the in-browser animated avatar works out of
the box, and the HeyGen video avatar works once you enter a HeyGen API key + avatar
id (section 8) — it just needs live testing with your own key and network/CSP
access to HeyGen. The only spec items not yet built are minor refinements
(proactive unprompted insights and a one-click management-summary bundle).
