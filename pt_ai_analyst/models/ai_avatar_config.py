# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiAvatarConfig(models.Model):
    """Single configuration record choosing how the on-screen avatar is rendered.

    - browser: a free, in-browser animated SVG avatar with lip-sync driven by the
      browser speech synthesizer (no external account).
    - heygen:  a realtime video avatar streamed from HeyGen (needs an API key and
      an avatar id). The key is stored here server-side and is only ever used by
      the token endpoint; it is never sent to the browser.
    """

    _name = "ai.avatar.config"
    _description = "AI Avatar Configuration"

    name = fields.Char(default="Avatar Configuration")
    avatar_mode = fields.Selection(
        selection=[
            ("browser", "In-browser animated avatar (free)"),
            ("heygen", "HeyGen realtime video avatar"),
        ],
        default="browser",
        required=True,
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    # HeyGen settings (only used when avatar_mode == 'heygen')
    heygen_api_key = fields.Char(
        string="HeyGen API Key",
        help="Stored server-side only; used to mint a short-lived streaming token. "
             "Never sent to the browser.",
    )
    heygen_avatar_id = fields.Char(
        string="HeyGen Avatar ID",
        help="The avatar identifier from your HeyGen account (Streaming Avatar).",
    )
    heygen_voice_id = fields.Char(string="HeyGen Voice ID")
    heygen_quality = fields.Selection(
        selection=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
        default="medium",
    )

    # Text-to-speech: how replies are voiced.
    tts_mode = fields.Selection(
        selection=[
            ("browser", "Browser voices (device-dependent)"),
            ("server", "Server / cloud voice (recommended on Linux)"),
        ],
        default="browser",
        required=True,
        help="On Linux/Ubuntu browsers often have no Arabic voice; the server "
             "option synthesizes natural audio server-side and plays it in the page.",
    )
    tts_provider = fields.Selection(
        selection=[
            ("google", "Google Cloud Text-to-Speech"),
            ("openai", "OpenAI-compatible (local: Piper / Kokoro / openedai-speech)"),
        ],
        default="google",
    )
    tts_api_base = fields.Char(
        string="TTS Base URL",
        help="For the OpenAI-compatible/local option, e.g. "
             "http://host.docker.internal:8000/v1 (a server exposing /audio/speech).",
    )
    tts_model = fields.Char(
        string="TTS Model", default="tts-1",
        help="Model name for the OpenAI-compatible speech server (e.g. tts-1, or a "
             "Piper/Kokoro model name depending on your server).",
    )
    tts_api_key = fields.Char(
        string="TTS API Key",
        help="Google: your Cloud TTS key. OpenAI-compatible/local: optional (many "
             "local servers ignore it). Stored server-side only.",
    )
    tts_voice_ar = fields.Char(
        string="Arabic Voice", default="ar-XA-Wavenet-B",
        help="Google: e.g. ar-XA-Wavenet-B. Local: the Arabic voice name your "
             "server exposes. Leave empty for the server default.",
    )
    tts_voice_en = fields.Char(
        string="English Voice", default="en-US-Wavenet-D",
        help="Google or local English voice name.",
    )

    @api.model
    def get_config(self):
        cfg = self.search([("company_id", "=", self.env.company.id)], limit=1)
        if not cfg:
            cfg = self.search([], limit=1)
        if not cfg:
            cfg = self.create({})
        return cfg

    @api.model
    def get_client_config(self):
        """Safe subset for the browser: never includes the API key."""
        cfg = self.get_config()
        return {
            "mode": cfg.avatar_mode,
            "heygen_avatar_id": cfg.heygen_avatar_id or "",
            "heygen_quality": cfg.heygen_quality or "medium",
            "heygen_configured": bool(cfg.heygen_api_key and cfg.heygen_avatar_id),
            "tts_mode": cfg.tts_mode,
            "tts_configured": bool(
                cfg.tts_mode == "server" and (
                    (cfg.tts_provider == "google" and cfg.tts_api_key)
                    or (cfg.tts_provider == "openai" and cfg.tts_api_base)
                )
            ),
        }
