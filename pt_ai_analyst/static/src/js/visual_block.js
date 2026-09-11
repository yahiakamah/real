/** @odoo-module **/

import { Component } from "@odoo/owl";

const PALETTE = [
    "#4a72d0", "#7a4ad0", "#2e9e6b", "#d08a2e", "#d0433a",
    "#2eb5d0", "#9e2e7a", "#6b8e23", "#8a8a8a", "#c04a8a",
];

/**
 * Renders one visual payload produced by the engine:
 *   { type: "kpi"|"table"|"bar"|"line"|"pie", title, ... }
 * All numbers come from the payload (engine-computed); this component only draws.
 */
export class VisualBlock extends Component {
    static template = "pt_ai_analyst.VisualBlock";
    static props = { payload: Object };

    get payload() {
        return this.props.payload || {};
    }

    color(i) {
        return PALETTE[i % PALETTE.length];
    }

    fmt(v) {
        if (typeof v === "number") {
            return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, {
                maximumFractionDigits: 2,
            });
        }
        return v === null || v === undefined ? "—" : v;
    }

    // ---- bar ----
    get bars() {
        const labels = this.payload.labels || [];
        const data = (this.payload.series?.[0]?.data) || [];
        const max = Math.max(1, ...data.map((d) => Math.abs(d) || 0));
        return labels.map((label, i) => ({
            label,
            value: data[i] || 0,
            pct: Math.round(((Math.abs(data[i]) || 0) / max) * 100),
            color: this.color(i),
        }));
    }

    // ---- line (SVG geometry) ----
    get line() {
        const W = 320, H = 130, pad = 22;
        const data = (this.payload.series?.[0]?.data) || [];
        const labels = this.payload.labels || [];
        if (!data.length) {
            return { points: "", dots: [], W, H, labels: [] };
        }
        const max = Math.max(...data), min = Math.min(...data, 0);
        const span = max - min || 1;
        const n = data.length;
        const xAt = (i) => (n === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (n - 1));
        const yAt = (v) => H - pad - ((v - min) / span) * (H - 2 * pad);
        const dots = data.map((v, i) => ({ x: xAt(i), y: yAt(v), value: v }));
        return {
            W, H,
            points: dots.map((d) => `${d.x},${d.y}`).join(" "),
            dots,
            baseline: H - pad,
            labels: labels.map((l, i) => ({ x: xAt(i), text: l })),
        };
    }

    // ---- pie (conic-gradient + legend) ----
    get pie() {
        const data = (this.payload.series?.[0]?.data) || [];
        const labels = this.payload.labels || [];
        const total = data.reduce((a, b) => a + (Math.abs(b) || 0), 0) || 1;
        let acc = 0;
        const stops = [];
        const legend = [];
        data.forEach((v, i) => {
            const start = (acc / total) * 100;
            acc += Math.abs(v) || 0;
            const end = (acc / total) * 100;
            const c = this.color(i);
            stops.push(`${c} ${start}% ${end}%`);
            legend.push({
                label: labels[i] || `#${i + 1}`,
                value: v,
                color: c,
                pct: Math.round(((Math.abs(v) || 0) / total) * 100),
            });
        });
        return { background: `conic-gradient(${stops.join(",")})`, legend };
    }
}
