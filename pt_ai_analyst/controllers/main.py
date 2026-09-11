# -*- coding: utf-8 -*-
import json
import logging

from odoo import http, _
from odoo.http import request, content_disposition

from ..engine.orchestrator import Orchestrator
from ..engine.exceptions import AiEngineError

_logger = logging.getLogger(__name__)

REQUIRED_GROUP = "pt_ai_analyst.group_ai_user"


class AiAnalystController(http.Controller):

    def _ensure_access(self):
        if not request.env.user.has_group(REQUIRED_GROUP):
            return False
        return True

    @http.route("/ai_analyst/bootstrap", type="json", auth="user")
    def bootstrap(self):
        """Initial data for the client action: suggestions + recent conversations."""
        if not self._ensure_access():
            return {"error": _("You do not have access to the AI Analyst.")}
        env = request.env
        suggestions = env["ai.suggested.question"].get_for_current_user()
        conversations = env["ai.conversation"].search_read(
            [("user_id", "=", env.user.id)],
            ["name", "last_message_date", "message_count"],
            limit=30,
            order="write_date desc",
        )
        return {
            "suggestions": suggestions,
            "conversations": conversations,
            "user_name": env.user.name,
            "avatar": env["ai.avatar.config"].get_client_config(),
        }

    @http.route("/ai_analyst/avatar/heygen_token", type="json", auth="user")
    def heygen_token(self):
        if not self._ensure_access():
            return {"error": _("Access denied.")}
        cfg = request.env["ai.avatar.config"].get_config()
        if cfg.avatar_mode != "heygen" or not cfg.heygen_api_key:
            return {"error": _("HeyGen is not configured.")}
        try:
            import requests
            resp = requests.post(
                "https://api.heygen.com/v1/streaming.create_token",
                headers={"X-Api-Key": cfg.heygen_api_key},
                timeout=30,
            )
            data = resp.json() if resp.content else {}
            token = (data.get("data") or {}).get("token")
            if not token:
                _logger.warning("HeyGen token response: %s", str(data)[:300])
                return {"error": _("Could not obtain a HeyGen session token.")}
            return {
                "token": token,
                "avatar_id": cfg.heygen_avatar_id or "",
                "voice_id": cfg.heygen_voice_id or "",
                "quality": cfg.heygen_quality or "medium",
            }
        except Exception:  # noqa: BLE001
            _logger.exception("HeyGen token request failed")
            return {"error": _("HeyGen token request failed.")}

    @http.route("/ai_analyst/messages", type="json", auth="user")
    def messages(self, conversation_id):
        if not self._ensure_access():
            return {"error": _("Access denied.")}
        conv = request.env["ai.conversation"].search(
            [("id", "=", conversation_id), ("user_id", "=", request.env.user.id)],
            limit=1,
        )
        if not conv:
            return {"error": _("Conversation not found.")}
        return {
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "payload": m.get_payload(),
                }
                for m in conv.message_ids
                if m.role in ("user", "assistant")
            ]
        }

    @http.route("/ai_analyst/ask", type="json", auth="user")
    def ask(self, question, conversation_id=None):
        if not self._ensure_access():
            return {"error": _("You do not have access to the AI Analyst.")}
        question = (question or "").strip()
        if not question:
            return {"error": _("Please enter a question.")}

        env = request.env
        Conversation = env["ai.conversation"]
        conv = False
        if conversation_id:
            conv = Conversation.search(
                [("id", "=", conversation_id), ("user_id", "=", env.user.id)], limit=1
            )
        if not conv:
            conv = Conversation.create({})

        conv.message_ids.create({
            "conversation_id": conv.id, "role": "user", "content": question,
        })

        try:
            provider = env["ai.provider"]._get_active_provider()
            orchestrator = Orchestrator(env, provider)
            history = conv.get_history_for_llm()
            # Drop the just-added user turn from history to avoid duplication.
            history = history[:-1] if history else []
            result = orchestrator.ask(question, history=history)
        except AiEngineError as exc:
            result = {"answer": None, "error": str(exc), "execution_time": 0,
                      "tool_calls": 0, "models": []}
        except Exception as exc:  # noqa: BLE001 -- never leak internals
            _logger.exception("AI Analyst failure")
            result = {"answer": None,
                      "error": _("Something went wrong while analysing the data. "
                                 "Please try again."),
                      "execution_time": 0, "tool_calls": 0, "models": []}

        answer = result.get("answer")
        error = result.get("error")
        visuals = result.get("visuals") or []

        assistant_msg = None
        if answer:
            assistant_msg = conv.message_ids.create({
                "conversation_id": conv.id,
                "role": "assistant",
                "content": answer,
                "execution_time": result.get("execution_time", 0),
                "payload": json.dumps({"visuals": visuals}) if visuals else False,
            })
        # Title the conversation from its first message once.
        if conv.name == _("New Conversation"):
            conv.action_rename_from_first_message()

        env["ai.audit.log"].log({
            "conversation_id": conv.id,
            "question": question,
            "models_accessed": ", ".join(result.get("models", [])),
            "tool_calls": result.get("tool_calls", 0),
            "execution_time": result.get("execution_time", 0),
            "success": bool(answer),
            "error_message": error or False,
        })

        return {
            "conversation_id": conv.id,
            "conversation_name": conv.name,
            "message_id": assistant_msg.id if assistant_msg else False,
            "answer": answer,
            "error": error,
            "visuals": visuals,
            "execution_time": result.get("execution_time", 0),
        }

    @http.route("/ai_analyst/tts", type="json", auth="user")
    def tts(self, text, lang=None):
        """Synthesize `text` to speech server-side (Google Cloud TTS) and return
        base64 audio. Keeps voice quality consistent regardless of the OS/browser
        (important on Linux, where browsers usually lack an Arabic voice)."""
        if not self._ensure_access():
            return {"error": _("Access denied.")}
        text = (text or "").strip()
        if not text:
            return {"error": _("Nothing to speak.")}
        text = text[:4000]  # keep requests bounded

        cfg = request.env["ai.avatar.config"].get_config()
        if cfg.tts_mode != "server":
            return {"error": _("Server voice is not configured.")}

        is_ar = (lang or "").lower().startswith("ar")
        provider = cfg.tts_provider or "google"

        try:
            import base64
            import requests
        except Exception:  # noqa: BLE001
            return {"error": _("Server missing the 'requests' library.")}

        # ---- OpenAI-compatible / local speech server (Piper, Kokoro, ...) ----
        if provider == "openai":
            base = (cfg.tts_api_base or "").rstrip("/")
            if not base:
                return {"error": _("Local TTS base URL is not set.")}
            url = base if base.endswith("/audio/speech") else base + "/audio/speech"
            voice = (cfg.tts_voice_ar if is_ar else cfg.tts_voice_en) or "alloy"
            headers = {"Content-Type": "application/json"}
            if cfg.tts_api_key:
                headers["Authorization"] = "Bearer %s" % cfg.tts_api_key
            try:
                resp = requests.post(
                    url, headers=headers,
                    json={
                        "model": cfg.tts_model or "tts-1",
                        "input": text,
                        "voice": voice,
                        "response_format": "mp3",
                    },
                    timeout=60,
                )
                if resp.status_code >= 400:
                    _logger.warning("Local TTS %s: %s", resp.status_code, resp.text[:300])
                    return {"error": _("The local voice service returned an error.")}
                audio = base64.b64encode(resp.content).decode("ascii")
                return {"audio": audio, "mime": "audio/mp3"}
            except Exception:  # noqa: BLE001
                _logger.exception("Local TTS failed")
                return {"error": _("The local voice service is unreachable.")}

        # ---- Google Cloud TTS ----
        if not cfg.tts_api_key:
            return {"error": _("Server voice is not configured.")}
        language_code = "ar-XA" if is_ar else "en-US"
        voice_name = (cfg.tts_voice_ar if is_ar else cfg.tts_voice_en) or ""
        voice = {"languageCode": language_code}
        if voice_name:
            voice["name"] = voice_name
        try:
            resp = requests.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                params={"key": cfg.tts_api_key},
                json={
                    "input": {"text": text},
                    "voice": voice,
                    "audioConfig": {"audioEncoding": "MP3"},
                },
                timeout=30,
            )
            if resp.status_code >= 400:
                _logger.warning("Google TTS %s: %s", resp.status_code, resp.text[:300])
                return {"error": _("The voice service returned an error.")}
            audio = (resp.json() or {}).get("audioContent")
            if not audio:
                return {"error": _("No audio was returned.")}
            return {"audio": audio, "mime": "audio/mp3"}
        except Exception:  # noqa: BLE001
            _logger.exception("Server TTS failed")
            return {"error": _("The voice service is unreachable.")}

    @http.route("/ai_analyst/conversation/rename", type="json", auth="user")
    def rename_conversation(self, conversation_id, name):
        if not self._ensure_access():
            return {"error": _("Access denied.")}
        conv = request.env["ai.conversation"].search(
            [("id", "=", conversation_id), ("user_id", "=", request.env.user.id)],
            limit=1,
        )
        if not conv:
            return {"error": _("Conversation not found.")}
        new_name = (name or "").strip()
        if new_name:
            conv.name = new_name
        return {"id": conv.id, "name": conv.name}

    @http.route("/ai_analyst/conversation/delete", type="json", auth="user")
    def delete_conversation(self, conversation_id):
        if not self._ensure_access():
            return {"error": _("Access denied.")}
        conv = request.env["ai.conversation"].search(
            [("id", "=", conversation_id), ("user_id", "=", request.env.user.id)],
            limit=1,
        )
        if not conv:
            return {"error": _("Conversation not found.")}
        conv.unlink()
        return {"deleted": True}

    @http.route("/ai_analyst/export/<int:message_id>/<string:fmt>",
                type="http", auth="user")
    def export(self, message_id, fmt, **kw):
        if not self._ensure_access():
            return request.not_found()
        msg = request.env["ai.message"].browse(message_id).exists()
        if not msg or msg.role != "assistant":
            return request.not_found()
        # Ownership: own conversation, or a manager.
        user = request.env.user
        if (msg.conversation_id.user_id != user
                and not user.has_group("pt_ai_analyst.group_ai_manager")):
            return request.not_found()

        fmt = (fmt or "").lower()
        if fmt == "csv":
            data = msg._export_csv_bytes()
            mimetype, ext = "text/csv", "csv"
        elif fmt in ("xlsx", "excel"):
            data = msg._export_xlsx_bytes()
            if data is None:
                return request.make_response(
                    _("Excel export needs the 'xlsxwriter' library on the server."),
                    headers=[("Content-Type", "text/plain; charset=utf-8")],
                )
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        elif fmt == "pdf":
            try:
                data, _ct = request.env["ir.actions.report"]._render_qweb_pdf(
                    "pt_ai_analyst.report_ai_message", [msg.id]
                )
            except Exception:  # noqa: BLE001 -- wkhtmltopdf may be missing
                _logger.exception("AI Analyst PDF export failed")
                return request.make_response(
                    _("PDF export is unavailable on this server (wkhtmltopdf)."),
                    headers=[("Content-Type", "text/plain; charset=utf-8")],
                )
            mimetype, ext = "application/pdf", "pdf"
        else:
            return request.not_found()

        filename = "ai_analyst_%s.%s" % (message_id, ext)
        return request.make_response(data, headers=[
            ("Content-Type", mimetype),
            ("Content-Disposition", content_disposition(filename)),
        ])
