# -*- coding: utf-8 -*-
"""Orchestrator.

Runs the plan -> execute -> explain loop:
  1. The LLM receives the user's question + the controlled tool schema.
  2. It calls tools (list_models / describe_model / run_aggregate / list_records).
  3. The engine executes each tool as the current user (ACL-safe) and returns data.
  4. The LLM writes the final answer grounded ONLY in that returned data.

The orchestrator never lets the LLM reach the ORM directly; it dispatches tool
calls to QueryEngine, which validates everything against the semantic layer.
"""
import logging
import time

from .providers import get_transport, AnthropicTransport
from .query_engine import QueryEngine
from .exceptions import AiEngineError, ProviderError

_logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4  # default ceiling; overridable per-provider (ai.provider.max_tool_rounds)


def _tool_schema():
    return [
        {
            "name": "list_models",
            "description": "List the business data areas (models) the user is "
                           "allowed to analyse, with their meaning and date field. "
                           "Call this first when you are unsure which data to use.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "describe_model",
            "description": "Get the available measures (aggregatable numbers) and "
                           "dimensions (groupable/filterable fields) for one model.",
            "input_schema": {
                "type": "object",
                "properties": {"model": {"type": "string"}},
                "required": ["model"],
            },
        },
        {
            "name": "run_aggregate",
            "description": "Run a read-only aggregation. Use for counts, sums, "
                           "averages, comparisons, rankings and trends over time.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {
                        "type": "array",
                        "description": "Odoo domain as a list of [field, operator, "
                                       "value] leaves; use '&'/'|'/'!' prefixes.",
                        "items": {},
                    },
                    "measures": {
                        "type": "array",
                        "description": "e.g. ['count'] or ['amount_total:sum', "
                                       "'turnaround:avg'].",
                        "items": {"type": "string"},
                    },
                    "group_by": {
                        "type": "array",
                        "description": "Dimensions, e.g. ['branch_id'] or "
                                       "['create_date:month'].",
                        "items": {"type": "string"},
                    },
                    "order": {"type": "string"},
                    "limit": {"type": "integer"},
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "last_7_days", "last_30_days",
                                 "last_90_days", "last_12_months", "this_week",
                                 "last_week", "this_month", "last_month",
                                 "this_quarter", "last_quarter", "this_year",
                                 "last_year"],
                        "description": "Optional relative date window applied on the "
                                       "model's date field.",
                    },
                },
                "required": ["model"],
            },
        },
        {
            "name": "compare_periods",
            "description": "Compare one measure across two time windows and get the "
                           "deltas (absolute and %) computed for you. Use for "
                           "'this month vs last', trends, and especially 'why did X "
                           "change?' -- pass a `breakdown` dimension to see which "
                           "part drove the change (sorted by biggest mover).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "measure": {
                        "type": "string",
                        "description": "'count' or 'field:func' (e.g. 'amount_total:sum').",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "last_7_days", "last_30_days",
                                 "last_90_days", "last_12_months", "this_week",
                                 "last_week", "this_month", "last_month",
                                 "this_quarter", "last_quarter", "this_year",
                                 "last_year"],
                    },
                    "compare_to": {
                        "type": "string",
                        "enum": ["previous_period", "previous_year"],
                    },
                    "breakdown": {
                        "type": "string",
                        "description": "Optional dimension to decompose the change by "
                                       "(e.g. 'branch_id', 'analysis_type_id').",
                    },
                },
                "required": ["model"],
            },
        },
        {
            "name": "list_records",
            "description": "List individual records (non-aggregated) with a hard "
                           "row cap. Use only when the user wants specific rows.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
                    "fields": {"type": "array", "items": {"type": "string"}},
                    "order": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["model"],
            },
        },
        {
            "name": "present_visual",
            "description": "Attach a KPI card, table or chart to your answer, built "
                           "from a previous run_aggregate result. Use it when a "
                           "visual makes the answer clearer (rankings -> bar, trends "
                           "over time -> line, shares of a whole -> pie, a single "
                           "headline number -> kpi). The numbers come from the "
                           "referenced result, so you never retype them.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "The 'ref' returned by the run_aggregate "
                                       "whose data to visualise.",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["kpi", "table", "bar", "line", "pie"],
                    },
                    "title": {"type": "string"},
                    "label_field": {
                        "type": "string",
                        "description": "The group_by field to use as labels / x-axis "
                                       "(omit for a single KPI total).",
                    },
                    "measure": {
                        "type": "string",
                        "description": "Which measure to plot, e.g. 'count' or "
                                       "'amount_total:sum'.",
                    },
                },
                "required": ["ref", "chart_type"],
            },
        },
    ]


class Orchestrator:
    def __init__(self, env, provider):
        self.env = env
        self.provider = provider
        self.engine = QueryEngine(env)
        self.transport = get_transport(provider)
        self.models_accessed = set()
        self.tool_call_count = 0
        self._results_cache = {}   # ref -> aggregate result
        self._agg_seq = 0
        self.visuals = []          # render payloads to attach to the answer
        self.max_rounds = max(1, min(getattr(provider, "max_tool_rounds", 4) or 4, 8))

    def _semantic_catalog_text(self):
        """Compact description of the enabled semantic models, embedded in the
        system prompt so the model can call run_aggregate/compare_periods directly
        without spending API rounds on list_models/describe_model."""
        try:
            models = self.engine.list_models()
        except Exception:  # noqa: BLE001
            return ""
        if not models:
            return ""
        lines = [
            "Available data — use these DIRECTLY with run_aggregate / "
            "compare_periods. Only call list_models / describe_model if you need "
            "something not shown here:",
        ]
        for m in models[:12]:
            try:
                d = self.engine.describe_model(m["model"])
            except Exception:  # noqa: BLE001
                continue
            measures = ["count"] + [x["field"] for x in d.get("measures", [])[:12]]
            dims = [x["field"] for x in d.get("dimensions", [])[:15]]
            biz = d.get("business_name") or m["model"]
            date = d.get("date_field") or "-"
            lines.append("- %s (model=%s, date_field=%s)" % (biz, m["model"], date))
            if measures:
                lines.append("    measures: " + ", ".join(measures))
            if dims:
                lines.append("    dimensions: " + ", ".join(dims))
        return "\n".join(lines)

    def _build_system_prompt(self):
        style = {
            "concise": "Keep answers concise.",
            "detailed": "Give detailed answers with the reasoning.",
            "executive": "Answer as an executive briefing: lead with the headline "
                         "KPIs, then the notable changes and any alerts.",
        }.get(self.provider.response_style, "Keep answers concise.")
        catalog = self._semantic_catalog_text()
        parts = [
            self.provider.system_instructions or "",
            "",
            "Hard rules (never violate):",
            "- Answer ONLY from data returned by the tools. Never invent figures.",
            "- If tools return no data, say the information is unavailable.",
            "- You are read-only. You cannot create, edit or delete anything.",
            "- Respect that the tools already enforce the user's permissions; if a "
            "  model is not listed, tell the user you don't have access to it.",
            "- Don't do period or delta arithmetic yourself; use compare_periods so "
            "  the numbers are computed from the data.",
            "",
            "How to answer:",
            "- When useful, structure the reply as: the direct ANSWER, the key DATA, "
            "  an INSIGHT (what the numbers indicate), and an optional RECOMMENDATION.",
            "- Clearly separate FACT (computed from data), INSIGHT (a conclusion you "
            "  drew from that data) and RECOMMENDATION (a suggestion). Never present "
            "  an inference or a suggestion as a fact.",
            "- For 'why did X change?' questions, use compare_periods with a breakdown "
            "  and explain the biggest contributing movers from the returned data.",
            "- Attach a visual with present_visual when it makes the answer clearer.",
            "- For a management summary or dashboard request, build a small dashboard: "
            "  a few KPI cards for the headline numbers, a period comparison, and the "
            "  top breakdowns -- each as its own present_visual call.",
            "- Detect and match the user's language (Arabic / Egyptian Arabic / "
            "  English).",
            style,
        ]
        if catalog:
            parts += ["", catalog]
        return "\n".join(parts)

    def _dispatch(self, name, args):
        self.tool_call_count += 1
        if name == "list_models":
            data = self.engine.list_models()
            self.models_accessed.update(m["model"] for m in data)
            return {"models": data}
        if name == "describe_model":
            model = args.get("model")
            self.models_accessed.add(model)
            return self.engine.describe_model(model)
        if name == "run_aggregate":
            self.models_accessed.add(args.get("model"))
            result = self.engine.run_aggregate(
                args.get("model"),
                domain=args.get("domain"),
                measures=args.get("measures"),
                group_by=args.get("group_by"),
                order=args.get("order"),
                limit=args.get("limit"),
                period=args.get("period"),
            )
            self._agg_seq += 1
            ref = "agg_%d" % self._agg_seq
            self._results_cache[ref] = result
            result["ref"] = ref
            return result
        if name == "compare_periods":
            self.models_accessed.add(args.get("model"))
            return self.engine.compare_periods(
                args.get("model"),
                measure=args.get("measure") or "count",
                period=args.get("period") or "this_month",
                compare_to=args.get("compare_to") or "previous_period",
                domain=args.get("domain"),
                breakdown=args.get("breakdown"),
            )
        if name == "present_visual":
            ref = args.get("ref")
            cached = self._results_cache.get(ref)
            if not cached:
                return {"error": "Unknown result reference; run an aggregate first."}
            if len(self.visuals) >= 6:
                return {"error": "Visual limit reached for this answer."}
            payload = self.engine.build_visual(
                cached,
                args.get("chart_type"),
                title=args.get("title") or "",
                label_field=args.get("label_field"),
                measure=args.get("measure"),
            )
            self.visuals.append(payload)
            return {"ok": True, "attached": payload.get("type")}
        if name == "list_records":
            self.models_accessed.add(args.get("model"))
            return self.engine.list_records(
                args.get("model"),
                domain=args.get("domain"),
                fields_=args.get("fields"),
                order=args.get("order"),
                limit=args.get("limit"),
            )
        return {"error": "unknown tool"}

    def ask(self, question, history=None):
        """Returns dict: {answer, error, execution_time, tool_calls, models}."""
        start = time.time()
        system = self._build_system_prompt()
        tools = _tool_schema()
        messages = list(history or [])
        # Ensure history ends on an assistant turn so adding the current user
        # question keeps roles alternating (required by some providers).
        while messages and messages[-1].get("role") == "user":
            messages.pop()
        messages.append({"role": "user", "content": question})

        is_anthropic = isinstance(self.transport, AnthropicTransport)
        final_text = ""
        try:
            for _round in range(self.max_rounds):
                result = self.transport.send(system, messages, tools)
                if not result["tool_calls"]:
                    final_text = result["text"]
                    break
                # Echo the assistant turn, then the tool results.
                messages.append(result["raw_assistant"])
                executed = []
                for call in result["tool_calls"]:
                    try:
                        output = self._dispatch(call["name"], call["input"])
                    except AiEngineError as exc:
                        output = {"error": str(exc)}
                    executed.append((call["id"], output))
                tool_msg = self.transport.format_tool_results(executed)
                if isinstance(tool_msg, list):
                    messages.extend(tool_msg)
                else:
                    messages.append(tool_msg)
            else:
                final_text = final_text or (
                    "I couldn't complete the analysis within the allowed steps."
                )
        except ProviderError as exc:
            return {
                "answer": None,
                "error": str(exc),
                "execution_time": round(time.time() - start, 3),
                "tool_calls": self.tool_call_count,
                "models": sorted(self.models_accessed),
                "visuals": self.visuals,
            }

        return {
            "answer": final_text or "I don't have enough data to answer that.",
            "error": None,
            "execution_time": round(time.time() - start, 3),
            "tool_calls": self.tool_call_count,
            "models": sorted(self.models_accessed),
            "visuals": self.visuals,
        }
