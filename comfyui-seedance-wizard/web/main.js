/**
 * main.js — ComfyUI Seedance Wizard extension entry point
 *
 * Registers a sidebar tab with an iframe loading wizard.html.
 *
 * Communication topology:
 *   wizard.html  <── postMessage ──>  main.js  <── fetch ──>  Python /seedance/* routes
 *   Python nodes.py ── WebSocket ──>  main.js  ── postMessage ──>  wizard.html
 *
 * postMessage protocol (wizard.html ↔ main.js):
 *   Outbound (wizard → main):
 *     { type: "seedance_rpc", id, route, method, body }
 *   Inbound (main → wizard):
 *     { type: "seedance_rpc_result", id, data }          — success
 *     { type: "seedance_rpc_result", id, error }         — failure
 *     { type: "seedance_ws", event, payload }            — WS push
 *
 * License: MIT
 * Copyright (c) 2025 Seedance Wizard Contributors
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ── Resolve ComfyUI PromptServer base URL ──────────────────────
// Handles custom ports (users sometimes run ComfyUI on non-8188 ports).
function getServerBase() {
    return `${window.location.protocol}//${window.location.host}`;
}

app.registerExtension({
    name: "seedance.wizard",

    async setup() {
        // ── Register the sidebar tab ────────────────────────────

        app.extensionManager.registerSidebarTab({
            id: "seedance.wizard",
            icon: "pi pi-video",
            title: "Seedance",
            tooltip: "AI Video Creation Wizard",
            type: "custom",
            render: (el) => {
                el.style.cssText =
                    "padding:0;overflow:hidden;display:flex;flex-direction:column;";

                const iframe = document.createElement("iframe");
                iframe.id    = "seedance-wizard-iframe";
                iframe.src   = "/extensions/comfyui-seedance-wizard/wizard.html";
                iframe.style.cssText =
                    "width:100%;height:100%;border:none;display:block;flex:1;";
                iframe.allow   = "clipboard-read;clipboard-write";
                iframe.sandbox = "allow-scripts allow-same-origin allow-forms";
                el.appendChild(iframe);
            },
        });

        // ── Helper: send a message to the wizard iframe ─────────

        function toIframe(msg) {
            const iframe = document.getElementById("seedance-wizard-iframe");
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.postMessage(msg, "*");
            }
        }

        // ── WebSocket events: Python → iframe ───────────────────
        // nodes.py pushes these via server.send_sync()

        const WS_EVENTS = [
            "seedance_video_progress",
            "seedance_video_complete",
            "seedance_error",
        ];

        WS_EVENTS.forEach((evtName) => {
            api.addEventListener(evtName, (event) => {
                toIframe({ type: "seedance_ws", event: evtName, payload: event.detail || {} });
            });
        });

        // ── RPC bridge: iframe → PromptServer ───────────────────
        //
        // wizard.html sends:
        //   { type: "seedance_rpc", id, route, method, body }
        //
        // main.js fetches the PromptServer route and replies with:
        //   { type: "seedance_rpc_result", id, data }   — on success
        //   { type: "seedance_rpc_result", id, error }  — on failure

        window.addEventListener("message", async (event) => {
            const msg = event.data;
            if (!msg || msg.type !== "seedance_rpc") return;

            const { id, route, method, body } = msg;
            if (!id || !route) return;

            try {
                // Build URL: route is like "/seedance/wizard/analyze"
                // or "/seedance/video/status?task_id=xxx"
                let url = route;
                if (!url.startsWith("/")) url = "/" + url;
                // Ensure it goes to the correct host (handles non-8188 ports)
                url = getServerBase() + url;

                const fetchOpts = {
                    method: (method || "POST").toUpperCase(),
                    headers: { "Content-Type": "application/json" },
                };
                if (body && fetchOpts.method !== "GET") {
                    fetchOpts.body = JSON.stringify(body);
                }

                const res  = await fetch(url, fetchOpts);
                let data;
                try {
                    data = await res.json();
                } catch {
                    data = {};
                }

                if (res.ok) {
                    toIframe({ type: "seedance_rpc_result", id, data });
                } else {
                    // Backend error — pass the error message through
                    const errMsg = (data && (data.message || data.error)) || `HTTP ${res.status}`;
                    toIframe({ type: "seedance_rpc_result", id, error: errMsg });
                }
            } catch (err) {
                console.error("[Seedance] RPC fetch failed:", err);
                toIframe({
                    type:  "seedance_rpc_result",
                    id,
                    error: err.message || "Network error",
                });
            }
        });

        console.log("[Seedance] Wizard v2 extension initialized");
    },
});
