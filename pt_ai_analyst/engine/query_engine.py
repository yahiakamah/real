# -*- coding: utf-8 -*-
"""Secure analytics engine.

This is the ONLY path through which the AI reaches the database. It:
  * exposes a small, controlled surface (list models, describe model, aggregate);
  * runs entirely through the Odoo ORM as the *current user*, so ACLs, record
    rules, company rules and multi-company boundaries are enforced automatically;
  * is strictly read-only -- it never calls create/write/unlink and never builds
    or executes SQL from AI input;
  * only touches models/fields flagged in the semantic layer;
  * caps result sizes so a large dataset can never be pulled into the AI context.

The AI proposes a *query plan* (model + domain + measures + group_by). The engine
validates every element of that plan against the semantic layer before running it.
"""
import logging
from datetime import datetime, timedelta

try:
    from dateutil.relativedelta import relativedelta
except ImportError:  # pragma: no cover
    relativedelta = None

from .exceptions import (
    ModelNotAllowed,
    FieldNotAllowed,
    QueryValidationError,
)

_logger = logging.getLogger(__name__)

# Operators the AI is allowed to use when building filter leaves. Deliberately
# excludes anything that could be abused; all are read-only comparisons.
ALLOWED_OPERATORS = {
    "=", "!=", ">", ">=", "<", "<=",
    "in", "not in", "like", "ilike", "=like", "=ilike",
    "child_of", "parent_of",
}
ALLOWED_MEASURE_FUNCS = {"count", "sum", "avg", "min", "max"}
ALLOWED_CHART_TYPES = {"kpi", "table", "bar", "line", "pie"}
MAX_GROUPS = 500          # cap read_group buckets returned to the AI
MAX_ROWS = 200            # cap raw record listings
DEFAULT_LIMIT = 50


class QueryEngine:
    def __init__(self, env):
        # env is the current user's environment -> security travels with it.
        self.env = env

    # ------------------------------------------------------------------
    # Visualisation (built from real aggregate rows, never from AI text)
    # ------------------------------------------------------------------
    @staticmethod
    def _measure_key(measure):
        if not measure or measure == "count":
            return "__count"
        return measure.split(":")[0]

    @staticmethod
    def _label_of(row, field):
        v = row.get(field)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return v[1]                       # many2one -> display name
        if v in (False, None, ""):
            return "—"
        return str(v)

    @classmethod
    def build_visual(cls, result, chart_type, title="", label_field=None, measure=None):
        """Turn a cached run_aggregate result into a render payload. All numbers
        come straight from `result['rows']` -- the AI only chooses the framing."""
        if chart_type not in ALLOWED_CHART_TYPES:
            chart_type = "table"
        rows = result.get("rows", []) or []
        group_by = result.get("group_by", []) or []
        if label_field and label_field not in group_by and rows:
            # Fall back to the first available grouping key present in the rows.
            label_field = group_by[0] if group_by else None
        mkey = cls._measure_key(measure)
        mlabel = "count" if mkey == "__count" else mkey

        if chart_type == "kpi":
            items = []
            if label_field:
                for r in rows:
                    items.append({"label": cls._label_of(r, label_field),
                                  "value": r.get(mkey)})
            else:
                total = sum((r.get(mkey) or 0) for r in rows) if rows else 0
                items.append({"label": title or "Total", "value": total})
            return {"type": "kpi", "title": title, "items": items[:12]}

        if chart_type == "table":
            columns = ([label_field] if label_field else []) + [mlabel]
            trows = []
            for r in rows:
                line = ([cls._label_of(r, label_field)] if label_field else [])
                line.append(r.get(mkey))
                trows.append(line)
            return {"type": "table", "title": title,
                    "columns": columns, "rows": trows[:200]}

        # bar / line / pie
        labels, data = [], []
        for i, r in enumerate(rows):
            labels.append(cls._label_of(r, label_field) if label_field else str(i + 1))
            data.append(r.get(mkey) or 0)
        return {
            "type": chart_type,
            "title": title,
            "labels": labels[:60],
            "series": [{"name": mlabel, "data": data[:60]}],
        }

    # ------------------------------------------------------------------
    # Relative dates + period-over-period comparison (insight engine)
    # ------------------------------------------------------------------
    CALENDAR_PERIODS = {"this_week", "last_week", "this_month", "last_month",
                        "this_quarter", "last_quarter", "this_year", "last_year"}
    ROLLING_PERIODS = {"today", "yesterday", "last_7_days", "last_30_days",
                       "last_90_days", "last_12_months"}

    @classmethod
    def _period_range(cls, period):
        """Resolve a period keyword to a [start, end) datetime pair. end is
        exclusive. Raises if the keyword is unknown."""
        if relativedelta is None:
            raise QueryValidationError("Date maths library unavailable.")
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = midnight + timedelta(days=1)

        if period == "today":
            return midnight, tomorrow
        if period == "yesterday":
            return midnight - timedelta(days=1), midnight
        if period == "last_7_days":
            return midnight - timedelta(days=6), tomorrow
        if period == "last_30_days":
            return midnight - timedelta(days=29), tomorrow
        if period == "last_90_days":
            return midnight - timedelta(days=89), tomorrow
        if period == "last_12_months":
            return midnight - relativedelta(months=12), tomorrow
        if period == "this_week":
            start = midnight - timedelta(days=midnight.weekday())
            return start, start + timedelta(days=7)
        if period == "last_week":
            start = midnight - timedelta(days=midnight.weekday() + 7)
            return start, start + timedelta(days=7)
        if period == "this_month":
            start = midnight.replace(day=1)
            return start, start + relativedelta(months=1)
        if period == "last_month":
            start = midnight.replace(day=1) - relativedelta(months=1)
            return start, start + relativedelta(months=1)
        if period == "this_quarter":
            q_month = ((midnight.month - 1) // 3) * 3 + 1
            start = midnight.replace(month=q_month, day=1)
            return start, start + relativedelta(months=3)
        if period == "last_quarter":
            q_month = ((midnight.month - 1) // 3) * 3 + 1
            start = midnight.replace(month=q_month, day=1) - relativedelta(months=3)
            return start, start + relativedelta(months=3)
        if period == "this_year":
            start = midnight.replace(month=1, day=1)
            return start, start + relativedelta(years=1)
        if period == "last_year":
            start = midnight.replace(month=1, day=1) - relativedelta(years=1)
            return start, start + relativedelta(years=1)
        raise QueryValidationError("Unsupported period '%s'." % period)

    @classmethod
    def _compare_range(cls, start, end, period, compare_to):
        """Given the current [start,end), return the comparison range."""
        if compare_to == "previous_year":
            return start - relativedelta(years=1), end - relativedelta(years=1)
        # previous_period (default)
        if period in cls.CALENDAR_PERIODS:
            shift = {
                "this_week": relativedelta(weeks=1), "last_week": relativedelta(weeks=1),
                "this_month": relativedelta(months=1), "last_month": relativedelta(months=1),
                "this_quarter": relativedelta(months=3), "last_quarter": relativedelta(months=3),
                "this_year": relativedelta(years=1), "last_year": relativedelta(years=1),
            }[period]
            return start - shift, end - shift
        span = end - start
        return start - span, start

    @staticmethod
    def _pct(current, previous):
        if not previous:
            return None
        return round((current - previous) / previous * 100.0, 1)

    def _date_domain(self, model_name, date_field, start, end):
        ftype = self.env[model_name]._fields[date_field].type
        if ftype == "date":
            fmt = "%Y-%m-%d"
            s, e = start.strftime(fmt), end.strftime(fmt)
        else:
            fmt = "%Y-%m-%d %H:%M:%S"
            s, e = start.strftime(fmt), end.strftime(fmt)
        return [(date_field, ">=", s), (date_field, "<", e)]

    def compare_periods(self, model_name, measure="count", period="this_month",
                        compare_to="previous_period", domain=None, breakdown=None):
        """Compare one measure across two time windows, computing deltas here so
        the AI never does the arithmetic. Optional `breakdown` decomposes the
        change by a dimension and sorts by biggest mover -- the backbone of
        'why did X change?' answers."""
        sem = self._get_semantic_model(model_name)
        date_field = sem.date_field
        if not date_field:
            raise QueryValidationError(
                "No date field is configured for this data, so it can't be compared over time."
            )
        measures_spec = self._validate_measures(sem, [measure])
        domain = self._validate_domain(sem, domain or [])
        base = self._parse_base_domain(sem)
        groupby = self._validate_group_by(sem, [breakdown]) if breakdown else []
        mkey = self._measure_key(measure)

        cur_start, cur_end = self._period_range(period)
        prev_start, prev_end = self._compare_range(cur_start, cur_end, period, compare_to)
        Model = self.env[model_name].sudo(False)

        def run(s, e):
            dom = base + domain + self._date_domain(model_name, date_field, s, e)
            return Model.read_group(dom, measures_spec, groupby, lazy=False, limit=MAX_GROUPS)

        cur_rows, prev_rows = run(cur_start, cur_end), run(prev_start, prev_end)

        def total(rows):
            return sum((r.get(mkey) or 0) for r in rows)

        cur_total, prev_total = total(cur_rows), total(prev_rows)
        result = {
            "model": model_name,
            "measure": "count" if mkey == "__count" else mkey,
            "current": {"from": str(cur_start.date()), "to": str(cur_end.date()),
                        "value": cur_total},
            "previous": {"from": str(prev_start.date()), "to": str(prev_end.date()),
                         "value": prev_total},
            "delta": cur_total - prev_total,
            "delta_pct": self._pct(cur_total, prev_total),
        }
        if breakdown:
            def index(rows):
                out = {}
                for r in rows:
                    out[self._label_of(r, breakdown)] = r.get(mkey) or 0
                return out
            ci, pi = index(cur_rows), index(prev_rows)
            labels = list(dict.fromkeys(list(ci) + list(pi)))
            bd = [{
                "label": lbl,
                "current": ci.get(lbl, 0),
                "previous": pi.get(lbl, 0),
                "delta": ci.get(lbl, 0) - pi.get(lbl, 0),
                "delta_pct": self._pct(ci.get(lbl, 0), pi.get(lbl, 0)),
            } for lbl in labels]
            bd.sort(key=lambda x: abs(x["delta"]), reverse=True)
            result["breakdown"] = bd[:20]
        return result

    # ------------------------------------------------------------------
    # Semantic-layer introspection tools (safe to expose to the AI)
    # ------------------------------------------------------------------
    def list_models(self):
        """Return the business catalogue the AI is allowed to reason about."""
        SemModel = self.env["ai.semantic.model"]
        records = SemModel.search([("ai_enabled", "=", True)])
        out = []
        for rec in records:
            # Only advertise models the current user can actually read.
            if not self._can_read(rec.model_name):
                continue
            out.append({
                "model": rec.model_name,
                "business_name": rec.name,
                "description": rec.description or "",
                "date_field": rec.date_field or "",
            })
        return out

    def _can_read(self, model_name):
        """Read-access check that works on Odoo 18 (has_access) and earlier
        (check_access_rights)."""
        if model_name not in self.env:
            return False
        Model = self.env[model_name]
        if hasattr(Model, "has_access"):
            try:
                return Model.has_access("read")
            except Exception:  # noqa: BLE001
                return False
        try:
            return Model.check_access_rights("read", raise_exception=False)
        except Exception:  # noqa: BLE001
            return False

    def describe_model(self, model_name):
        sem = self._get_semantic_model(model_name)
        measures, dimensions = [], []
        for f in sem.field_ids.filtered("ai_enabled"):
            entry = {
                "field": f.field_name,
                "label": f.business_name or f.field_label,
                "type": f.ttype,
                "sensitive": f.is_sensitive,
            }
            if f.is_measure:
                measures.append(entry)
            if f.is_dimension:
                dimensions.append(entry)
        return {
            "model": sem.model_name,
            "business_name": sem.name,
            "description": sem.description or "",
            "date_field": sem.date_field or "",
            "measures": measures,
            "dimensions": dimensions,
        }

    # ------------------------------------------------------------------
    # The one analytical operation the AI can run
    # ------------------------------------------------------------------
    def run_aggregate(self, model_name, domain=None, measures=None,
                      group_by=None, order=None, limit=None, period=None):
        """Validated, ACL-safe aggregation via ORM read_group.

        measures: list of "field:func" (e.g. "amount_total:sum") or "count".
        group_by: list of dimension specs (e.g. "branch_id", "date:month").
        period: optional relative-date keyword (e.g. "this_month") applied on the
                model's configured date field.
        """
        sem = self._get_semantic_model(model_name)
        Model = self.env[model_name].sudo(False)  # explicit: run as current user

        domain = self._validate_domain(sem, domain or [])
        base_domain = self._parse_base_domain(sem)
        full_domain = base_domain + domain
        if period:
            if not sem.date_field:
                raise QueryValidationError(
                    "No date field is configured for this data."
                )
            start, end = self._period_range(period)
            full_domain = full_domain + self._date_domain(
                model_name, sem.date_field, start, end
            )

        group_by = self._validate_group_by(sem, group_by or [])
        fields_spec = self._validate_measures(sem, measures or ["count"])

        # read_group already enforces record rules + ACLs.
        try:
            results = Model.read_group(
                domain=full_domain,
                fields=fields_spec,
                groupby=group_by,
                orderby=order or None,
                limit=min(limit or MAX_GROUPS, MAX_GROUPS),
                lazy=False,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("AI aggregate failed on %s: %s", model_name, exc)
            raise QueryValidationError(
                "The requested analysis could not be executed on this data."
            )

        return {
            "model": model_name,
            "domain": full_domain,
            "group_by": group_by,
            "measures": measures or ["count"],
            "row_count": len(results),
            "rows": self._clean_rows(results, group_by),
        }

    def list_records(self, model_name, domain=None, fields_=None, order=None, limit=None):
        """Constrained raw listing (e.g. 'show me the 10 delayed analyses'). Only
        AI-enabled, non-sensitive-by-default fields; hard row cap."""
        sem = self._get_semantic_model(model_name)
        Model = self.env[model_name].sudo(False)
        domain = self._validate_domain(sem, domain or [])
        base_domain = self._parse_base_domain(sem)
        allowed_fields = {
            f.field_name for f in sem.field_ids.filtered(
                lambda x: x.ai_enabled and not x.is_sensitive
            )
        }
        requested = [f for f in (fields_ or []) if f in allowed_fields]
        if not requested:
            requested = list(allowed_fields)[:8]
        records = Model.search_read(
            domain=base_domain + domain,
            fields=requested,
            order=order or None,
            limit=min(limit or DEFAULT_LIMIT, MAX_ROWS),
        )
        return {"model": model_name, "row_count": len(records), "rows": records}

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _get_semantic_model(self, model_name):
        sem = self.env["ai.semantic.model"].search(
            [("model_name", "=", model_name), ("ai_enabled", "=", True)], limit=1
        )
        if not sem:
            raise ModelNotAllowed(
                "This information is not available to the assistant."
            )
        if model_name not in self.env:
            raise ModelNotAllowed("This information is not available.")
        return sem

    def _allowed_field_names(self, sem):
        return {f.field_name: f for f in sem.field_ids.filtered("ai_enabled")}

    def _validate_domain(self, sem, domain):
        """Only accept a flat list of [field, op, value] leaves and '&'/'|'/'!'.
        Every field must be an AI-enabled field of this model."""
        allowed = self._allowed_field_names(sem)
        clean = []
        for leaf in domain:
            if leaf in ("&", "|", "!"):
                clean.append(leaf)
                continue
            if not (isinstance(leaf, (list, tuple)) and len(leaf) == 3):
                raise QueryValidationError("Malformed filter.")
            field, op, value = leaf
            base_field = str(field).split(".")[0]
            if base_field not in allowed:
                raise FieldNotAllowed(
                    "The filter refers to a field the assistant cannot use."
                )
            if op not in ALLOWED_OPERATORS:
                raise QueryValidationError("Unsupported filter operator.")
            clean.append((field, op, value))
        return clean

    def _validate_group_by(self, sem, group_by):
        allowed = self._allowed_field_names(sem)
        clean = []
        for spec in group_by:
            base = str(spec).split(":")[0]
            f = allowed.get(base)
            if not f or not f.is_dimension:
                raise FieldNotAllowed(
                    "Cannot group by the requested field."
                )
            clean.append(spec)
        return clean

    def _validate_measures(self, sem, measures):
        allowed = self._allowed_field_names(sem)
        spec = []
        for m in measures:
            if m == "count":
                spec.append("__count")
                continue
            if ":" not in m:
                raise QueryValidationError("Measure must be 'field:func' or 'count'.")
            field, func = m.split(":", 1)
            if func not in ALLOWED_MEASURE_FUNCS:
                raise QueryValidationError("Unsupported aggregation function.")
            f = allowed.get(field)
            if not f or not f.is_measure:
                raise FieldNotAllowed("Cannot aggregate the requested field.")
            spec.append("%s:%s" % (field, func))
        # read_group needs measure fields; drop the pseudo '__count'.
        return [s for s in spec if s != "__count"]

    def _parse_base_domain(self, sem):
        if not sem.default_domain:
            return []
        try:
            from odoo.tools.safe_eval import safe_eval
            parsed = safe_eval(sem.default_domain)
            return parsed if isinstance(parsed, list) else []
        except Exception:  # noqa: BLE001
            _logger.warning("Invalid base domain on %s", sem.model_name)
            return []

    @staticmethod
    def _clean_rows(results, group_by):
        """Trim read_group noise so only the requested dimensions + measures reach
        the AI context (keeps token usage low, avoids leaking internals)."""
        keep_meta = {"__count"}
        rows = []
        for r in results:
            row = {}
            for k, v in r.items():
                if k.startswith("__") and k not in keep_meta:
                    continue
                if k in ("__domain",):
                    continue
                row[k] = v
            rows.append(row)
        return rows
