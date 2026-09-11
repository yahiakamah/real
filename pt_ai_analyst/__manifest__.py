# -*- coding: utf-8 -*-
{
    "name": "PomoTech AI Analyst (THE EXPERT)",
    "summary": "Database-aware conversational AI analyst with a human-like avatar, "
               "built as a secure, read-only intelligence layer over existing Odoo data.",
    "description": """
PomoTech AI Analyst
===================
A conversational, database-aware AI analyst that lets users ask natural-language
questions (Arabic / Egyptian Arabic / English) about authorized Odoo data and
receive explained, data-grounded answers through a human-like avatar.

Architecture (Phase 1 foundation):
  * AI Provider abstraction (no vendor lock-in, no hardcoded credentials)
  * Semantic layer (business meaning of models / fields, measures & dimensions,
    sensitive-field flags, per-model AI enablement)
  * Secure analytics engine (read-only, ORM read_group, respects ACL + record
    rules; never runs raw or AI-generated SQL)
  * Orchestrator with a controlled tool set (list models / describe model /
    run aggregate); the LLM plans, Odoo executes, the LLM explains
  * Conversation memory, message history and audit logging
  * OWL chat client action with avatar states

This module is intentionally domain-agnostic (extensible to CRM, Sales, HR,
Manufacturing, ...). The laboratory / analysis domain is the first target and is
configured entirely through the semantic layer -- no model names are hardcoded.
""",
    "author": "PomoTech",
    "website": "https://pomotech-eg.com",
    "category": "Productivity/Discuss",
    "version": "18.0.1.0.0",
    "license": "OPL-1",
    "depends": ["base", "web", "mail"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ai_security.xml",
        "security/ir.model.access.csv",
        "data/ai_provider_data.xml",
        "data/ai_suggested_question_data.xml",
        "views/ai_provider_views.xml",
        "views/ai_semantic_views.xml",
        "views/ai_avatar_config_views.xml",
        "views/ai_conversation_views.xml",
        "views/ai_audit_views.xml",
        "views/ai_suggested_question_views.xml",
        "views/ai_analyst_client_action.xml",
        "views/ai_analyst_menus.xml",
        "report/ai_message_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pt_ai_analyst/static/src/scss/ai_analyst.scss",
            "pt_ai_analyst/static/src/js/**/*.js",
            "pt_ai_analyst/static/src/xml/**/*.xml",
        ],
    },
    "application": True,
    "installable": True,
}
