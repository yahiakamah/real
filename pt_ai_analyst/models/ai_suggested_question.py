# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiSuggestedQuestion(models.Model):
    """Contextual starter questions shown when the assistant opens. Filtered by
    the required security group so users only see prompts they can actually run."""

    _name = "ai.suggested.question"
    _description = "AI Suggested Question"
    _order = "sequence, id"

    name = fields.Char(string="Question", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(default="fa-line-chart", help="Font Awesome class.")
    group_id = fields.Many2one(
        "res.groups",
        string="Required Group",
        help="If set, only users in this group see the suggestion.",
    )

    @api.model
    def get_for_current_user(self, limit=8):
        records = self.search([]).filtered(
            lambda q: not q.group_id or q.group_id in self.env.user.groups_id
        )
        return [{"id": r.id, "name": r.name, "icon": r.icon} for r in records[:limit]]
