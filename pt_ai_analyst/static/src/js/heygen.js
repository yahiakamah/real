/** @odoo-module **/

/**
 * HeyGen realtime video avatar helper.
 *
 * Loads the HeyGen Streaming Avatar SDK at runtime, opens a streaming session
 * using a short-lived token minted server-side (the API key never reaches the
 * browser), attaches the video stream to a <video> element, and speaks answers.
 *
 * Everything is wrapped so a failure never breaks the app — the caller falls
 * back to the in-browser animated avatar. Needs network access to HeyGen and,
 * depending on your deployment, its domains allowed in the page CSP.
 */
export class HeyGenAvatar {
    constructor() {
        this.avatar = null;
        this.ready = false;
        this.TaskType = null;
    }

    async init({ token, avatarId, quality, videoEl, onStart, onStop, onError }) {
        try {
            const mod = await import("https://esm.sh/@heygen/streaming-avatar");
            const StreamingAvatar = mod.default || mod.StreamingAvatar;
            const StreamingEvents = mod.StreamingEvents || {};
            this.TaskType = mod.TaskType || null;

            this.avatar = new StreamingAvatar({ token });

            if (StreamingEvents.STREAM_READY) {
                this.avatar.on(StreamingEvents.STREAM_READY, (event) => {
                    if (videoEl && event?.detail) {
                        videoEl.srcObject = event.detail;
                        videoEl.play?.().catch(() => {});
                    }
                });
            }
            if (StreamingEvents.AVATAR_START_TALKING) {
                this.avatar.on(StreamingEvents.AVATAR_START_TALKING,
                    () => onStart && onStart());
            }
            if (StreamingEvents.AVATAR_STOP_TALKING) {
                this.avatar.on(StreamingEvents.AVATAR_STOP_TALKING,
                    () => onStop && onStop());
            }
            if (StreamingEvents.STREAM_DISCONNECTED) {
                this.avatar.on(StreamingEvents.STREAM_DISCONNECTED,
                    () => { this.ready = false; });
            }

            await this.avatar.createStartAvatar({
                quality: quality || "medium",
                avatarName: avatarId,
            });
            this.ready = true;
            return true;
        } catch (err) {
            this.ready = false;
            onError && onError(err);
            return false;
        }
    }

    async speak(text) {
        if (!this.avatar || !this.ready || !text) { return; }
        try {
            const taskType = this.TaskType?.REPEAT || "repeat";
            await this.avatar.speak({ text, taskType });
        } catch { /* ignore individual speak errors */ }
    }

    async stop() {
        try { await this.avatar?.stopAvatar?.(); } catch { /* noop */ }
        this.ready = false;
        this.avatar = null;
    }
}
