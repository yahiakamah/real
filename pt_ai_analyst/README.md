# PomoTech AI Analyst — `pt_ai_analyst`

A database-aware conversational AI analyst for Odoo 18. Users ask natural-language
questions (Arabic / Egyptian Arabic / English) about **authorized** Odoo data and
get explained, data-grounded answers through a human-like avatar.

This is **Phase 1: the foundation** — a real, installable module implementing the
security-critical core of the spec. Voice, animated avatars and rich charts are
scoped as later phases (see Roadmap). Nothing here fabricates data or bypasses
Odoo security.

---

## What's inside (Phase 1)

| Area | Delivered |
|------|-----------|
| **Provider abstraction** (§35) | `ai.provider` — **Google Gemini** (default), Anthropic, or any OpenAI-compatible endpoint; model, temperature, tokens, system prompt, per-company default. No hardcoded credentials. |
| **Semantic layer** (§27) | `ai.semantic.model` / `ai.semantic.field` — register which models/fields the AI may see, mark measures / dimensions / sensitive fields, "Discover Fields" button. **No model names are hardcoded.** |
| **Secure analytics engine** (§4, 16, 19, 29) | `engine/query_engine.py` — read-only, runs through the ORM **as the current user** (ACLs + record rules enforced), `read_group`-based aggregation, operator whitelist, row/bucket caps. Never builds or runs SQL from AI input. |
| **Orchestrator** (§18, 20, 28) | `engine/orchestrator.py` — controlled tool-use loop (list models / describe model / aggregate / list records). The LLM plans, Odoo executes, the LLM explains, grounded only in returned data. |
| **Voice interaction** (§13, 14, 33) | Talk to the avatar and hear it reply **in the same language** (Arabic / English), via the browser Web Speech API — no external keys. Mic (speech-to-text) + spoken answers (text-to-speech); avatar syncs listening / speaking. Toggleable, degrades gracefully where unsupported. |
| **Conversation memory & management** (§6, 26) | `ai.conversation` / `ai.message`, auto-titling, recent-turn context, plus in-UI **search / rename / delete / continue**. |
| **Audit log** (§37) | `ai.audit.log` — user, question, models accessed, tool calls, timing, success. Stores the *operation*, not sensitive rows. |
| **Reporting & export** (§24, §25) | Any answer with data exports to **CSV / Excel / PDF** (`/ai_analyst/export/<msg>/<fmt>`), built from the message's stored payload — the real numbers, never regenerated. PDF via a QWeb report. |
| **Security** (§16) | Three groups (User / Manager / Admin), record rules on conversations **and messages**, ACL. |
| **Visual analytics** (§11) | `present_visual` tool + engine `build_visual` + OWL `VisualBlock`: KPI cards, tables, bar / line / pie — rendered inline in the chat. Numbers come from the referenced `run_aggregate` result, never retyped by the model. |
| **Insight & explainability** (§9, §10, §20, §21) | `compare_periods` tool + engine-computed deltas (absolute & %), relative-date resolver, and change decomposition by dimension ("biggest mover"). System prompt enforces the ANSWER / DATA / INSIGHT / RECOMMENDATION structure and FACT vs INSIGHT vs RECOMMENDATION separation; executive-briefing style. |
| **UI** (§12, 15, 31, 32) | OWL client action: history sidebar, avatar with lifecycle states (idle / thinking / analyzing / speaking / error), chat bubbles, suggested questions, inline visuals. |
| **Error handling** (§30) | Human-friendly errors; tracebacks/SQL never reach the browser. |

---

## Install

1. Copy `pt_ai_analyst` into your addons path.
2. `pip install requests` on the Odoo server (listed in `external_dependencies`).
3. Update Apps list → install **PomoTech AI Analyst**.
4. Add yourself to **Settings → Users → AI Analyst / Administrator**.

## Configure (5 minutes)

1. **AI Analyst → Configuration → Providers** → open *Default Provider* → set the
   **API Key** (and adjust model if needed).
2. **AI Analyst → Configuration → Semantic Layer** → *New* → pick a model
   (e.g. your analysis/order model) → **Discover Fields** → tick the measures,
   dimensions and sensitive fields → set the **Primary Date Field**.
3. Repeat for each model you want the AI to reason over (branches, invoices, …).
4. Open **AI Analyst → Assistant** and ask away.

> The AI can only ever touch models/fields you enable in the semantic layer, and
> only rows the logged-in user is already permitted to read.

---

## Security model (how "never bypass Odoo security" is guaranteed)

- Every query runs on `self.env[model]` under the **current user** — Odoo applies
  ACLs, record rules and multi-company rules automatically.
- The engine is **read-only**: only `read_group` / `search_read`, never
  create/write/unlink, never `cr.execute`, never AI-generated SQL.
- Domains from the AI are validated leaf-by-leaf against an **operator whitelist**
  and the semantic field list; unknown fields/operators are rejected.
- Result sizes are capped so a large table can't be pulled into the AI context.
- The API key lives only on the provider record — never sent to the browser or
  stored in conversation/audit logs.

---

## Roadmap (later phases)

These are architected-for but intentionally **not** built yet:

- **Phase 2 — Visual analytics (§11) ✅ delivered:** KPI cards, tables and
  bar / line / pie charts render inline in the chat, built from real aggregate
  data. Dynamic multi-widget dashboards (§22) are the remaining part.
- **Phase 3 — Insight & explainability engine (§9, 10, 21) ✅ delivered:**
  period-over-period comparison with deltas computed in the engine, relative-date
  resolution, and "why did X change" decomposition by dimension; responses
  structured as FACT / INSIGHT / RECOMMENDATION with an executive-briefing style.
  Proactive unprompted insights and a one-call management-summary bundle remain.
- **Phase 4 — Reporting & export (§24, 25) ✅ delivered:** CSV / Excel / PDF of any
  answer, from the stored payload. Excel needs `xlsxwriter` on the server; PDF needs
  `wkhtmltopdf` (both degrade to a friendly message if absent). Scheduled/emailed
  reports remain.
- **Phase 5 — Voice (§13, 14, 33) ✅ delivered:** browser-native speech in and out,
  replies in the user's language, avatar synced to listening / speaking, toggleable.
- **Phase 6 — Avatar ✅ delivered (two modes):** an in-browser **animated SVG
  avatar** that blinks and lip-syncs while speaking (free, default), and a full
  **HeyGen realtime video avatar** integration (server-minted token, streaming
  SDK, speaks the answers) selectable in Configuration → Avatar. HeyGen needs your
  API key + avatar id and live testing; it falls back to the animated avatar if it
  can't start.
- **Dashboards (§22) ✅ delivered:** multiple visuals from one answer render in a
  responsive grid; a management-summary request builds a KPI+charts dashboard.
- **Proactive unprompted insights / one-call management-summary bundle (§21)**
  remain as refinements.

---

## Notes / assumptions

- Module named `pt_ai_analyst` (generic engine, extensible beyond one domain per
  §34); the target domain is configured entirely through the semantic layer.
- **Three provider transports ship**: Gemini (default), Anthropic, OpenAI-compatible.
  Gemini declares the Odoo `domain` as a JSON-encoded string (its schema validator
  rejects heterogeneous arrays) and the transport parses it back automatically.
- `read_group` is the Odoo 18 public aggregation API used here. If you later move
  to `_read_group`/`formatted_read_group`, only `query_engine.run_aggregate`
  changes.
- Default model string (`gemini-2.5-pro`) is a placeholder — set the model your
  API key is entitled to.
- End-to-end behavior needs a live Odoo 18 + a real provider key to test; the code
  is written against Odoo 18 conventions but has not been run against a live DB.

