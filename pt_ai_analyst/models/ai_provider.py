# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AiProvider(models.Model):
    """Configurable AI provider / model. No credentials are hardcoded; the API
    key lives only on this record and is never sent to the browser or stored in
    conversation logs."""

    _name = "ai.provider"
    _description = "AI Provider Configuration"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string="Default",
        help="The provider used when a request does not specify one. "
             "Only one provider should be the default per company.",
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )

    provider_type = fields.Selection(
        selection=[
            ("gemini", "Google Gemini (generateContent)"),
            ("anthropic", "Anthropic (Messages API)"),
            ("openai", "OpenAI-compatible (Chat Completions)"),
        ],
        string="Provider",
        required=True,
        default="gemini",
    )
    model = fields.Char(
        required=True,
        default="gemini-3.6-flash",
        help="Model identifier as expected by the provider's API.",
    )
    api_base_url = fields.Char(
        string="API Base URL",
        help="Override the default endpoint. Leave empty to use the provider default.",
    )
    api_key = fields.Char(
        string="API Key",
        help="Stored server-side only. Never exposed to the client or the AI context.",
    )

    temperature = fields.Float(default=0.0)
    max_tokens = fields.Integer(string="Max Tokens", default=1024)
    request_timeout = fields.Integer(string="Timeout (s)", default=60)
    max_tool_rounds = fields.Integer(
        string="Max Tool Rounds", default=4,
        help="How many plan/execute steps the AI may take per question. Each step "
             "is one API request, so a lower number uses less quota (good for free "
             "tiers) but may cut off very complex questions. 4 is a good balance.",
    )

    system_instructions = fields.Text(
        string="System Instructions",
        help="Base persona / guardrails prepended to every request. The engine "
             "adds strict anti-hallucination and read-only rules automatically.",
        default=lambda self: self._default_system_instructions(),
    )

    default_language = fields.Selection(
        selection=[
            ("auto", "Auto-detect"),
            ("ar", "Arabic"),
            ("en", "English"),
        ],
        default="auto",
    )
    response_style = fields.Selection(
        selection=[
            ("concise", "Concise"),
            ("detailed", "Detailed"),
            ("executive", "Executive briefing"),
        ],
        default="concise",
    )

    @api.model
    def _default_system_instructions(self):
        return (
            "You are a professional, database-aware data analyst embedded inside "
            "an Odoo ERP. You answer strictly from data returned by the provided "
            "tools. You never invent numbers, records, customers, revenue, dates "
            "or results. If the tools return no data, you say the information is "
            "unavailable. You clearly separate FACT (computed from data), INSIGHT "
            "(a conclusion drawn from that data) and RECOMMENDATION (a suggestion). "
            "You detect the user's language and answer in it (Arabic, Egyptian "
            "Arabic or English), in a concise, professional and friendly tone."
        )

    @api.constrains("is_default", "company_id")
    def _check_single_default(self):
        for provider in self.filtered("is_default"):
            dup = self.search_count(
                [
                    ("is_default", "=", True),
                    ("company_id", "=", provider.company_id.id),
                    ("id", "!=", provider.id),
                ]
            )
            if dup:
                raise UserError(
                    _("Only one default AI provider is allowed per company.")
                )

    @api.model
    def _get_active_provider(self, company=None):
        company = company or self.env.company
        provider = self.search(
            [("is_default", "=", True), ("company_id", "=", company.id)], limit=1
        )
        if not provider:
            provider = self.search([("company_id", "=", company.id)], limit=1)
        if not provider:
            raise UserError(
                _("No AI provider is configured. Please configure one in "
                  "AI Analyst > Configuration > Providers.")
            )
        if not provider.api_key:
            raise UserError(
                _("The AI provider '%s' has no API key configured.") % provider.name
            )
        return provider
