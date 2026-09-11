/** @odoo-module **/

/**
 * Thin wrapper over the browser's Web Speech API so the avatar can listen and
 * speak "through the screen" with no external keys. Degrades gracefully: if the
 * browser lacks a capability, the matching `*Supported` flag is false and the UI
 * hides that control.
 *
 * Language: recognition takes an explicit BCP-47 lang hint; speech picks the best
 * installed voice for the answer's detected language, so replies come back in the
 * same language the user used.
 */
export class SpeechEngine {
    constructor() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.SR = SR || null;
        this.synth = window.speechSynthesis || null;
        this.recognition = null;
        this._voices = [];
        if (this.synth) {
            const load = () => { this._voices = this.synth.getVoices() || []; };
            load();
            // Voices often load asynchronously.
            this.synth.addEventListener?.("voiceschanged", load);
        }
    }

    get sttSupported() { return !!this.SR; }
    get ttsSupported() { return !!this.synth; }

    startListening(lang, { onresult, onend, onerror } = {}) {
        if (!this.SR) { return false; }
        this.stopListening();
        const rec = new this.SR();
        rec.lang = lang || "ar-EG";
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.continuous = false;
        rec.onresult = (e) => {
            const transcript = e.results?.[0]?.[0]?.transcript || "";
            onresult && onresult(transcript);
        };
        rec.onerror = (e) => onerror && onerror(e.error);
        rec.onend = () => { this.recognition = null; onend && onend(); };
        this.recognition = rec;
        try {
            rec.start();
        } catch {
            this.recognition = null;
            return false;
        }
        return true;
    }

    stopListening() {
        if (this.recognition) {
            try { this.recognition.stop(); } catch { /* noop */ }
            this.recognition = null;
        }
    }

    pickVoice(lang) {
        if (!this._voices.length && this.synth) {
            this._voices = this.synth.getVoices() || [];
        }
        const low = (lang || "").toLowerCase();
        const base = low.split("-")[0];
        return (
            this._voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(low)) ||
            this._voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(base)) ||
            (base === "ar"
                ? this._voices.find((v) => /arab|العرب/i.test(v.name || ""))
                : null) ||
            null
        );
    }

    hasVoiceFor(lang) {
        if (!this._voices.length && this.synth) {
            this._voices = this.synth.getVoices() || [];
        }
        const base = (lang || "").toLowerCase().split("-")[0];
        return (
            this._voices.some((v) => v.lang && v.lang.toLowerCase().startsWith(base)) ||
            (base === "ar" && this._voices.some((v) => /arab|العرب/i.test(v.name || "")))
        );
    }

    speak(text, lang, { onstart, onend } = {}) {
        if (!this.synth || !text) { onend && onend(); return; }
        this.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.lang = lang || "ar-EG";
        const v = this.pickVoice(u.lang);
        if (v) { u.voice = v; }
        u.rate = 1.0;
        u.onstart = () => onstart && onstart();
        u.onend = () => onend && onend();
        u.onerror = () => onend && onend();
        this.synth.speak(u);
    }

    cancel() {
        if (this.synth) {
            try { this.synth.cancel(); } catch { /* noop */ }
        }
    }
}

/** Detect the reply language from its text so TTS speaks it correctly. */
export function detectLang(text) {
    return /[\u0600-\u06FF]/.test(text || "") ? "ar-EG" : "en-US";
}
