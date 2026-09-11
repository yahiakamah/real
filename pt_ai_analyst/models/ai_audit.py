# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiAuditLog(models.Model):
    """Records analytical AI activity for governance. Deliberately stores the
    analytical *operation* (which models / measures / filters) rather than raw
    sensitive result rows."""

    _name = "ai.audit.log"
    _description = "AI Audit Log"
    _order = "create_date desc"

    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    conversation_id = fields.Many2one("ai.conversation", ondelete="set null")
    question = fields.Text()
    intent = fields.Char(string="Detected Intent")
    models_accessed = fields.Char(string="Models Accessed")
    operation = fields.Char(help="Aggregation / grouping / comparison summary.")
    tool_calls = fields.Integer(string="Tool Calls")
    execution_time = fields.Float(string="Execution Time (s)")
    success = fields.Boolean(default=True)
    error_message = fields.Char()

    @api.model
    def log(self, vals):
        """Create an audit entry in its own transaction-safe way. Callers pass a
        plain dict; failures here must never break the user's answer."""
        try:
            return self.sudo().create(vals)
        except Exception:  # noqa: BLE001 -- audit must never raise to the user
            return self.browse()
