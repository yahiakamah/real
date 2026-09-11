# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AiSemanticModel(models.Model):
    """Describes which Odoo models the AI is allowed to analyse and what they
    mean in business terms. This is the ONLY source of truth for what the AI can
    touch -- a model that is not enabled here is invisible to the engine."""

    _name = "ai.semantic.model"
    _description = "AI Semantic Model"
    _order = "name"

    name = fields.Char(string="Business Name", required=True)
    model_id = fields.Many2one(
        "ir.model", string="Odoo Model", required=True, ondelete="cascade"
    )
    model_name = fields.Char(related="model_id.model", store=True, string="Technical Model")
    ai_enabled = fields.Boolean(
        string="Enabled for AI", default=True,
        help="If unchecked, the AI cannot query this model at all.",
    )
    description = fields.Text(
        string="Business Meaning",
        help="Plain-language description exposed to the AI so it understands the "
             "model without inspecting the raw schema each time.",
    )
    date_field = fields.Char(
        string="Primary Date Field",
        help="Default field used for date grouping / relative-date filters "
             "(e.g. create_date, date_order, request_date).",
    )
    default_domain = fields.Char(
        string="Base Domain",
        help="Optional Python domain always AND-ed onto queries for this model "
             "(e.g. [('state','!=','cancel')]).",
    )
    field_ids = fields.One2many(
        "ai.semantic.field", "semantic_model_id", string="Fields"
    )
    field_count = fields.Integer(compute="_compute_field_count")

    _sql_constraints = [
        ("unique_model", "unique(model_id)", "This model is already registered."),
    ]

    @api.depends("field_ids")
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    @api.onchange("model_id")
    def _onchange_model_id(self):
        if self.model_id and not self.name:
            self.name = self.model_id.name

    def action_discover_fields(self):
        """Populate the field catalogue from ir.model.fields. Never assumes field
        names -- it reads whatever the target model actually exposes and lets the
        admin flag measures / dimensions / sensitivity afterwards."""
        Field = self.env["ir.model.fields"]
        analytic_types = {"integer", "float", "monetary"}
        dimension_types = {"many2one", "selection", "char", "date", "datetime", "boolean"}
        for rec in self:
            existing = set(rec.field_ids.mapped("field_id").ids)
            vals = []
            fields_recs = Field.search([("model_id", "=", rec.model_id.id)])
            for f in fields_recs:
                if f.id in existing or f.name.startswith("__"):
                    continue
                is_measure = f.ttype in analytic_types and f.name != "id"
                is_dimension = f.ttype in dimension_types
                vals.append({
                    "semantic_model_id": rec.id,
                    "field_id": f.id,
                    "is_measure": is_measure,
                    "is_dimension": is_dimension,
                    "ai_enabled": not f.name.startswith(("message_", "activity_")),
                })
            if vals:
                self.env["ai.semantic.field"].create(vals)
        return True


class AiSemanticField(models.Model):
    """Per-field metadata: whether the AI may see it, whether it is a measure
    (aggregatable) or a dimension (groupable), and whether it is sensitive."""

    _name = "ai.semantic.field"
    _description = "AI Semantic Field"
    _order = "semantic_model_id, field_label"

    semantic_model_id = fields.Many2one(
        "ai.semantic.model", required=True, ondelete="cascade"
    )
    model_id = fields.Many2one(related="semantic_model_id.model_id", store=True)
    field_id = fields.Many2one(
        "ir.model.fields", string="Field", required=True, ondelete="cascade",
        domain="[('model_id', '=', model_id)]",
    )
    field_name = fields.Char(related="field_id.name", store=True)
    field_label = fields.Char(related="field_id.field_description", store=True, string="Label")
    ttype = fields.Selection(related="field_id.ttype", store=True, string="Type")

    business_name = fields.Char(help="Optional business-friendly alias for the AI.")
    ai_enabled = fields.Boolean(string="Visible to AI", default=True)
    is_measure = fields.Boolean(
        string="Measure", help="Can be aggregated (SUM/AVG/MIN/MAX)."
    )
    is_dimension = fields.Boolean(
        string="Dimension", help="Can be used for grouping / filtering."
    )
    is_sensitive = fields.Boolean(
        string="Sensitive",
        help="Extra-restricted (personal / medical / financial). Never returned "
             "unless the current user passes the ACL check anyway; treated with "
             "minimal exposure.",
    )

    _sql_constraints = [
        (
            "unique_field_per_model",
            "unique(semantic_model_id, field_id)",
            "This field is already registered for the model.",
        ),
    ]
