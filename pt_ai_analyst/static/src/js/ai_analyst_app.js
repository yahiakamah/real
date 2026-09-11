/** @odoo-module **/

import { Component, useState, onWillStart, useRef, onPatched, onWillUnmount, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { VisualBlock } from "./visual_block";
import { SpeechEngine, detectLang } from "./voice";
import { HeyGenAvatar } from "./heygen";

export class AiAnalystApp extends Component {
    static template = "pt_ai_analyst.AiAnalystApp";
    static components = { VisualBlock };
    static props = ["*"];

    setup() {
        this.notification = useService("notification");
        this.threadRef = useRef("thread");
        this.avatarVideoRef = useRef("avatarVideo");
        this.speech = new SpeechEngine();
        this.heygen = null;
        this._warnedNoArVoice = false;
        this._audio = null;
        this.state = useState({
            status: "idle",
            input: "",
            messages: [],
            conversations: [],
            suggestions: [],
            activeConversationId: null,
            userName: "",
            loading: false,
            listening: false,
            voiceEnabled: true,
            handsFree: this.speech.sttSupported,
            inputLang: "ar-EG",
            search: "",
            editingId: null,
            editingName: "",
            avatarMode: "browser",
            avatarConfig: {},
            ttsMode: "browser",
            ttsConfigured: false,
        });

        onWillStart(async () => {
            const data = await rpc("/ai_analyst/bootstrap", {});
            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
                return;
            }
            this.state.suggestions = data.suggestions || [];
            this.state.conversations = data.conversations || [];
            this.state.userName = data.user_name || "";
            const avatar = data.avatar || {};
            this.state.avatarConfig = avatar;
            this.state.avatarMode =
                avatar.mode === "heygen" && avatar.heygen_configured ? "heygen" : "browser";
            this.state.ttsMode = avatar.tts_mode || "browser";
            this.state.ttsConfigured = !!avatar.tts_configured;
        });

        onMounted(() => {
            if (this.state.avatarMode === "heygen") { this._initHeyGen(); }
            // Hands-free: begin listening on open (may prompt for mic permission).
            this._maybeListen();
        });

        onPatched(() => this._scrollToBottom());
        onWillUnmount(() => {
            this.speech.stopListening();
            this.speech.cancel();
            this.heygen?.stop();
        });
    }

    // ---------------- helpers ----------------
    _scrollToBottom() {
        const el = this.threadRef.el;
        if (el) { el.scrollTop = el.scrollHeight; }
    }

    get sttSupported() { return this.speech.sttSupported; }
    get ttsSupported() { return this.speech.ttsSupported; }
    get canSpeak() {
        return this.state.avatarMode === "browser"
            && (this.ttsSupported
                || (this.state.ttsMode === "server" && this.state.ttsConfigured));
    }

    get avatarStatusLabel() {
        return {
            idle: this.state.handsFree ? _t("Ready — just speak") : _t("Ready"),
            listening: _t("Listening…"),
            thinking: _t("Thinking…"),
            analyzing: _t("Analyzing the data…"),
            speaking: _t("Speaking…"),
            error: _t("Something went wrong"),
        }[this.state.status];
    }

    get filteredConversations() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) { return this.state.conversations; }
        return this.state.conversations.filter(
            (c) => (c.name || "").toLowerCase().includes(q)
        );
    }

    exportUrl(messageId, fmt) {
        return `/ai_analyst/export/${messageId}/${fmt}`;
    }

    // ---------------- conversations ----------------
    async newConversation() {
        this.speech.cancel();
        this.state.activeConversationId = null;
        this.state.messages = [];
        this.state.status = "idle";
        this._maybeListen();
    }

    async selectConversation(conv) {
        if (this.state.editingId === conv.id) { return; }
        this.state.activeConversationId = conv.id;
        this.state.loading = true;
        const data = await rpc("/ai_analyst/messages", { conversation_id: conv.id });
        this.state.loading = false;
        if (data.error) {
            this.notification.add(data.error, { type: "danger" });
            return;
        }
        this.state.messages = (data.messages || []).map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            visuals: (m.payload && m.payload.visuals) || [],
        }));
    }

    startEdit(conv) {
        this.state.editingId = conv.id;
        this.state.editingName = conv.name || "";
    }

    async commitEdit(conv) {
        const name = (this.state.editingName || "").trim();
        this.state.editingId = null;
        if (!name || name === conv.name) { return; }
        const data = await rpc("/ai_analyst/conversation/rename", {
            conversation_id: conv.id, name,
        });
        if (data && data.name) { conv.name = data.name; }
    }

    onEditKeydown(ev, conv) {
        if (ev.key === "Enter") { ev.preventDefault(); this.commitEdit(conv); }
        else if (ev.key === "Escape") { this.state.editingId = null; }
    }

    async deleteConversation(conv) {
        if (!window.confirm(_t("Delete this conversation?"))) { return; }
        const data = await rpc("/ai_analyst/conversation/delete", {
            conversation_id: conv.id,
        });
        if (data && data.deleted) {
            this.state.conversations = this.state.conversations.filter(
                (c) => c.id !== conv.id
            );
            if (this.state.activeConversationId === conv.id) { this.newConversation(); }
        }
    }

    // ---------------- HeyGen ----------------
    async _initHeyGen() {
        const tok = await rpc("/ai_analyst/avatar/heygen_token", {});
        if (!tok || tok.error) {
            this.notification.add(
                _t("Video avatar unavailable — using the animated avatar instead."),
                { type: "warning" }
            );
            this.state.avatarMode = "browser";
            return;
        }
        this.heygen = new HeyGenAvatar();
        const ok = await this.heygen.init({
            token: tok.token,
            avatarId: tok.avatar_id,
            quality: tok.quality,
            videoEl: this.avatarVideoRef.el,
            onStart: () => (this.state.status = "speaking"),
            onStop: () => { this.state.status = "idle"; this._maybeListen(); },
            onError: () => {
                this.notification.add(
                    _t("Video avatar failed to start — using the animated avatar."),
                    { type: "warning" }
                );
                this.state.avatarMode = "browser";
            },
        });
        if (!ok) { this.state.avatarMode = "browser"; }
    }

    // ---------------- voice ----------------
    toggleVoice() {
        this.state.voiceEnabled = !this.state.voiceEnabled;
        if (!this.state.voiceEnabled) { this.speech.cancel(); }
    }

    toggleHandsFree() {
        this.state.handsFree = !this.state.handsFree;
        if (this.state.handsFree) { this._maybeListen(); }
        else { this.speech.stopListening(); this.state.listening = false; }
    }

    toggleInputLang() {
        this.state.inputLang = this.state.inputLang === "ar-EG" ? "en-US" : "ar-EG";
    }

    /** Start listening if hands-free conditions allow (idle, not busy/speaking). */
    _maybeListen() {
        if (!this.state.handsFree || !this.sttSupported) { return; }
        if (this.state.listening || this.state.loading) { return; }
        if (this.state.status === "speaking") { return; }
        this._beginListen();
    }

    _beginListen() {
        const ok = this.speech.startListening(this.state.inputLang, {
            onresult: (text) => {
                this.state.listening = false;
                if (text) { this.state.input = text; this.ask(); }
            },
            onend: () => {
                this.state.listening = false;
                if (this.state.status === "listening") { this.state.status = "idle"; }
                // Silence/timeout with no result: in hands-free, listen again.
                if (this.state.handsFree && this.state.status === "idle"
                    && !this.state.loading) {
                    setTimeout(() => this._maybeListen(), 700);
                }
            },
            onerror: (err) => {
                this.state.listening = false;
                if (this.state.status === "listening") { this.state.status = "idle"; }
                // 'not-allowed' => mic permission denied; stop hands-free to avoid a loop.
                if (err === "not-allowed" || err === "service-not-allowed") {
                    this.state.handsFree = false;
                    this.notification.add(
                        _t("Microphone blocked — allow it and use the mic button."),
                        { type: "warning" }
                    );
                }
            },
        });
        if (ok) { this.state.listening = true; this.state.status = "listening"; }
    }

    micClick() {
        if (this.state.listening) {
            this.speech.stopListening();
            this.state.listening = false;
            if (this.state.status === "listening") { this.state.status = "idle"; }
            return;
        }
        this.speech.cancel();
        this._beginListen();
    }

    _stopAudio() {
        if (this._audio) {
            try { this._audio.pause(); } catch { /* noop */ }
            this._audio = null;
        }
    }

    async _serverSpeak(answer, lang) {
        this.state.status = "speaking";
        let res;
        try {
            res = await rpc("/ai_analyst/tts", { text: answer, lang });
        } catch {
            res = { error: "unreachable" };
        }
        if (!res || res.error || !res.audio) {
            // Fall back to browser voice, then to silence.
            if (this.state.voiceEnabled && this.ttsSupported) {
                this.speech.speak(answer, lang, {
                    onstart: () => (this.state.status = "speaking"),
                    onend: () => { this.state.status = "idle"; this._maybeListen(); },
                });
                return;
            }
            this.state.status = "idle";
            this._maybeListen();
            return;
        }
        this._stopAudio();
        const audio = new Audio(`data:${res.mime || "audio/mp3"};base64,${res.audio}`);
        this._audio = audio;
        audio.onended = () => { this.state.status = "idle"; this._maybeListen(); };
        audio.onerror = () => { this.state.status = "idle"; this._maybeListen(); };
        audio.play().catch(() => { this.state.status = "idle"; this._maybeListen(); });
    }

    _speakAnswer(answer) {
        if (this.state.avatarMode === "heygen" && this.heygen?.ready) {
            this.state.status = "speaking";
            this.heygen.speak(answer);
            return true;
        }
        if (!this.state.voiceEnabled) { return false; }
        const lang = detectLang(answer);

        // Server-side cloud voice (recommended on Linux).
        if (this.state.ttsMode === "server" && this.state.ttsConfigured) {
            this._serverSpeak(answer, lang);
            return true;
        }

        // Browser voice.
        if (this.ttsSupported) {
            if (lang.startsWith("ar") && !this.speech.hasVoiceFor("ar")
                && !this._warnedNoArVoice) {
                this._warnedNoArVoice = true;
                this.notification.add(
                    _t("No Arabic voice on this device. On Linux, either install "
                       + "espeak-ng and use Firefox, or switch Voice to the server "
                       + "option in Configuration → Avatar."),
                    { type: "warning" }
                );
            }
            this.speech.speak(answer, lang, {
                onstart: () => (this.state.status = "speaking"),
                onend: () => { this.state.status = "idle"; this._maybeListen(); },
            });
            return true;
        }
        return false;
    }

    // ---------------- ask ----------------
    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.ask(); }
    }

    selectSuggestion(text) {
        this.state.input = text;
        this.ask();
    }

    async ask() {
        const question = (this.state.input || "").trim();
        if (!question || this.state.loading) { return; }
        this.speech.stopListening();
        this.state.listening = false;
        this.speech.cancel();
        this._stopAudio();
        this.state.messages.push({ role: "user", content: question });
        this.state.input = "";
        this.state.loading = true;
        this.state.status = "thinking";

        const analyzeTimer = setTimeout(() => {
            if (this.state.loading) { this.state.status = "analyzing"; }
        }, 500);

        let data;
        try {
            data = await rpc("/ai_analyst/ask", {
                question,
                conversation_id: this.state.activeConversationId,
            });
        } catch {
            clearTimeout(analyzeTimer);
            this.state.status = "error";
            this.state.loading = false;
            this.state.messages.push({
                role: "assistant",
                content: _t("The assistant is unavailable right now. Please try again."),
                is_error: true,
            });
            setTimeout(() => this._maybeListen(), 800);
            return;
        }
        clearTimeout(analyzeTimer);
        this.state.loading = false;

        if (data.error) {
            this.state.status = "error";
            this.state.messages.push({
                role: "assistant", content: data.error, is_error: true,
            });
            setTimeout(() => this._maybeListen(), 800);
            return;
        }

        this.state.activeConversationId = data.conversation_id;
        this.state.messages.push({
            id: data.message_id,
            role: "assistant",
            content: data.answer,
            visuals: data.visuals || [],
        });
        this._refreshConversationList(data);

        const spoke = data.answer ? this._speakAnswer(data.answer) : false;
        if (!spoke) {
            this.state.status = "idle";
            this._maybeListen();
        }
    }

    _refreshConversationList(data) {
        const existing = this.state.conversations.find(
            (c) => c.id === data.conversation_id
        );
        if (existing) {
            existing.name = data.conversation_name;
        } else {
            this.state.conversations.unshift({
                id: data.conversation_id,
                name: data.conversation_name,
                message_count: this.state.messages.length,
            });
        }
    }
}

registry.category("actions").add("pt_ai_analyst.assistant", AiAnalystApp);
