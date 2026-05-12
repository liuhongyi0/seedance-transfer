"""
nodes.py — ComfyUI Seedance Wizard core module

Contains:
  - SeedanceWizardNode: main output node (video path)
  - SeedanceApiKeyNode: optional API key configuration node
  - PromptServer route handlers: forward requests to Node.js backend
  - Configuration management: read/write seedance_config.json
  - API client: authenticated HTTP forwarding to Node.js backend

All routes are prefixed with /seedance. The HTML wizard panel fetches
to localhost:8188/seedance/*, and this module attaches the Bearer token
before forwarding to the Node.js backend.

License: MIT
Copyright (c) 2025 Seedance Wizard Contributors
"""

import os
import json
import time
import logging
import threading
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

logger = logging.getLogger("seedance.nodes")

# ──────────────────────────────────────────────
# Module-level state (shared across node instances)
# ──────────────────────────────────────────────

_wizard_state: Dict[str, Any] = {
    "current_task_id": None,
    "task_status": None,
    "video_url": None,
    "video_path": None,
    "last_error": None,
}


def _reset_wizard_state():
    """Reset the shared wizard state for a new generation cycle."""
    _wizard_state["current_task_id"] = None
    _wizard_state["task_status"] = None
    _wizard_state["video_url"] = None
    _wizard_state["video_path"] = None
    _wizard_state["last_error"] = None


# ──────────────────────────────────────────────
# Configuration management
# ──────────────────────────────────────────────

DEFAULT_CONFIG = {
    "api_key": "",
    "backend_url": "http://localhost:3000",
    "language": "zh",
    "last_session_id": "",
}


def _get_comfyui_base_path() -> str:
    """Resolve ComfyUI root directory."""
    try:
        import folder_paths
        return folder_paths.base_path
    except ImportError:
        # Fallback: walk up from this file's location
        path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            if os.path.exists(os.path.join(path, "main.py")) or \
               os.path.exists(os.path.join(path, "comfy")):
                return path
            path = os.path.dirname(path)
        logger.warning("Could not find ComfyUI root; using cwd as fallback")
        return os.getcwd()


def _get_config_path() -> str:
    """Get the path to the seedance configuration file."""
    base = _get_comfyui_base_path()
    config_dir = os.path.join(base, "user", "default")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "seedance_config.json")


def load_config() -> dict:
    """Load the seedance configuration from disk."""
    path = _get_config_path()
    config = dict(DEFAULT_CONFIG)

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            config.update(stored)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to parse config file %s: %s", path, e)

    # Environment variable override for backend_url
    env_url = os.environ.get("SEEDANCE_BACKEND_URL")
    if env_url:
        config["backend_url"] = env_url

    return config


def save_config(updates: dict) -> None:
    """Merge updates into the configuration and write to disk."""
    config = load_config()
    config.update(updates)
    path = _get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("Seedance config saved to %s", path)
    except OSError as e:
        logger.error("Failed to save config: %s", e)
        raise


def get_api_key() -> str:
    """Return the configured API key (may be empty string)."""
    return load_config().get("api_key", "")


def get_backend_url() -> str:
    """Return the configured backend URL."""
    return load_config().get("backend_url", DEFAULT_CONFIG["backend_url"])


# ──────────────────────────────────────────────
# API Client (synchronous HTTP forwarding)
# ──────────────────────────────────────────────

class SeedanceApiClient:
    """Synchronous HTTP client that forwards requests to the Node.js backend
    with Bearer token authentication."""

    def __init__(self, api_key: str, backend_url: str):
        self.api_key = api_key
        self.backend_url = backend_url.rstrip("/")
        self._timeout = 120  # seconds

    def _build_headers(self, content_type: str = "application/json") -> dict:
        headers = {"Content-Type": content_type}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def forward(self, method: str, path: str, data: Optional[dict] = None,
                params: Optional[dict] = None) -> tuple:
        """Forward a request to the backend. Returns (response_dict, status_code)."""
        url = f"{self.backend_url}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        headers = self._build_headers()
        body = None
        if data is not None and method.upper() != "GET":
            body = json.dumps(data).encode("utf-8")

        logger.debug("Forwarding %s %s", method.upper(), url)

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    result = {"raw": raw}
                return result, status

        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = e.read().decode("utf-8")
                result = json.loads(body)
            except Exception:
                result = {"error": "HTTP_ERROR", "message": str(e)}
            return result, status

        except urllib.error.URLError as e:
            logger.error("Connection to backend failed: %s", e)
            return {
                "error": "CONNECTION_ERROR",
                "message": f"Cannot reach backend at {self.backend_url}. Is it running?"
            }, 503

        except Exception as e:
            logger.error("Unexpected error forwarding request: %s", e)
            return {"error": "FORWARD_ERROR", "message": str(e)}, 500


def _get_client() -> SeedanceApiClient:
    """Build a client from the current configuration."""
    return SeedanceApiClient(get_api_key(), get_backend_url())


# ──────────────────────────────────────────────
# PromptServer route registration
# ──────────────────────────────────────────────

def _register_routes():
    """Register all /seedance/* routes on the ComfyUI PromptServer.
    Called at module import time."""
    try:
        from server import PromptServer
        from aiohttp import web
        routes = PromptServer.instance.routes
    except Exception as e:
        logger.warning("PromptServer not available; skipping route registration: %s", e)
        return

    # ── Helper: forward a request and return JSON ──

    async def _forward_json(request: web.Request, method: str, path: str) -> web.Response:
        """Parse JSON body, forward to backend, return JSON response."""
        try:
            body = await request.json() if request.can_read_body else None
        except Exception:
            body = None

        client = _get_client()
        result, status = client.forward(method, path, data=body)

        # Push WebSocket events for video status changes
        _maybe_push_ws_event(path, result)

        return web.json_response(result, status=status)

    def _maybe_push_ws_event(path: str, result: dict):
        """If the response contains video progress info, push a WebSocket event."""
        try:
            from server import PromptServer
            server = PromptServer.instance

            # /api/video/generate → push initial progress
            if "/api/video/generate" in path and "task_id" in result:
                _wizard_state["current_task_id"] = result.get("task_id")
                _wizard_state["task_status"] = "queued"
                server.send_sync("seedance_video_progress", {
                    "task_id": result.get("task_id"),
                    "status": "queued",
                    "progress": 0,
                    "message": "Task queued...",
                })

            # /api/video/{id}/status → push progress updates
            elif "/status" in path:
                status = result.get("status", "")
                progress = result.get("progress", 0)
                task_id = result.get("task_id", "")
                _wizard_state["task_status"] = status

                if status == "completed":
                    server.send_sync("seedance_video_complete", {
                        "task_id": task_id,
                        "video_url": result.get("video_url", ""),
                        "estimated_cost_fen": result.get("estimated_cost_fen"),
                        "actual_cost_fen": result.get("actual_cost_fen"),
                        "message": "Video generation complete!",
                    })
                elif status == "failed":
                    server.send_sync("seedance_error", {
                        "code": "GENERATION_FAILED",
                        "message": result.get("error", "Video generation failed"),
                        "task_id": task_id,
                    })
                else:
                    server.send_sync("seedance_video_progress", {
                        "task_id": task_id,
                        "status": status,
                        "progress": progress,
                        "message": f"{status.capitalize()} ({progress}%)",
                    })

            # Check for error responses
            if result.get("code") == "INSUFFICIENT_BALANCE":
                server.send_sync("seedance_error", {
                    "code": "INSUFFICIENT_BALANCE",
                    "message": result.get("message", "Insufficient balance"),
                })

        except Exception as e:
            logger.debug("WebSocket push skipped: %s", e)

    # ── Wizard routes ──

    # ── 新向导: 图片+想法 → 结构化参数 + Flux 预览 ──
    @routes.post("/seedance/wizard/analyze")
    async def wizard_analyze(request: web.Request):
        return await _forward_json(request, "POST", "/api/wizard/analyze")

    # ── 旧向导（兼容保留）──
    @routes.post("/seedance/wizard/start")
    async def wizard_start(request: web.Request):
        return await _forward_json(request, "POST", "/api/wizard/start")

    @routes.post("/seedance/wizard/message")
    async def wizard_message(request: web.Request):
        return await _forward_json(request, "POST", "/api/wizard/message")

    @routes.post("/seedance/wizard/preview")
    async def wizard_preview(request: web.Request):
        return await _forward_json(request, "POST", "/api/wizard/preview")

    # ── Video routes ──

    @routes.post("/seedance/video/generate")
    async def video_generate(request: web.Request):
        return await _forward_json(request, "POST", "/api/video/generate")

    @routes.get("/seedance/video/status")
    async def video_status(request: web.Request):
        task_id = request.rel_url.query.get("task_id", "")
        path = f"/api/video/{task_id}/status"
        client = _get_client()
        result, status = client.forward("GET", path)
        _maybe_push_ws_event(path, result)
        return web.json_response(result, status=status)

    @routes.get("/seedance/video/result")
    async def video_result(request: web.Request):
        task_id = request.rel_url.query.get("task_id", "")
        path = f"/api/video/{task_id}/result"
        client = _get_client()
        result, status = client.forward("GET", path)
        return web.json_response(result, status=status)

    # ── Balance（新向导状态栏使用）──

    @routes.get("/seedance/balance")
    async def get_balance(request: web.Request):
        client = _get_client()
        result, status = client.forward("GET", "/api/balance")
        return web.json_response(result, status=status)

    # ── Estimate ──

    @routes.post("/seedance/estimate")
    async def estimate(request: web.Request):
        return await _forward_json(request, "POST", "/api/estimate")

    # ── Settings routes ──

    @routes.get("/seedance/settings")
    async def get_settings(request: web.Request):
        config = load_config()
        api_key = config.get("api_key", "")
        return web.json_response({
            "api_key_configured": bool(api_key),
            "api_key_prefix": (api_key[:14] + "...") if len(api_key) > 14 else api_key,
            "backend_url": config.get("backend_url", DEFAULT_CONFIG["backend_url"]),
            "language": config.get("language", "zh"),
        })

    @routes.get("/seedance/locale")
    async def get_locale(request: web.Request):
        config = load_config()
        return web.json_response({
            "locale": config.get("language", DEFAULT_CONFIG["language"]),
        })

    @routes.post("/seedance/settings")
    async def post_settings(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "BAD_REQUEST", "message": "Invalid JSON"}, status=400)

        updates = {}
        if "api_key" in body:
            updates["api_key"] = body["api_key"]
        if "backend_url" in body:
            updates["backend_url"] = body["backend_url"]
        if "language" in body:
            updates["language"] = body["language"]

        try:
            save_config(updates)
            return web.json_response({"ok": True, "message": "Settings saved"})
        except OSError as e:
            return web.json_response({"error": "SAVE_FAILED", "message": str(e)}, status=500)

    logger.info("Seedance Wizard routes registered on PromptServer")


# Register routes at import time
_register_routes()


# ──────────────────────────────────────────────
# ComfyUI Node: SeedanceWizardNode
# ──────────────────────────────────────────────

class SeedanceWizardNode:
    """
    Main Seedance Wizard output node.

    This node acts as the Python-side host for the HTML wizard panel.
    It holds internal state (current task_id) and, when triggered,
    polls the backend until video generation completes, downloads
    the result, and outputs the video file path.

    The primary interaction is through the HTML wizard sidebar panel.
    This node is the final output carrier within the ComfyUI workflow.
    """

    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    OUTPUT_NODE = True
    FUNCTION = "wait_for_video"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("INT", {"default": 0, "min": 0, "max": 999999,
                                    "tooltip": "Increment to trigger video generation"}),
            },
            "optional": {
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Override API key (leave empty to use config file)"
                }),
            }
        }

    def wait_for_video(self, trigger: int, api_key: str = "") -> tuple:
        """Poll for video completion, download, and return the file path.

        When trigger is 0 or no task is in progress, returns an empty string.
        When a task is active (submitted by the wizard UI), polls until
        complete or failed, downloads the video, and returns its path.
        """
        task_id = _wizard_state.get("current_task_id")
        if not task_id:
            logger.debug("SeedanceWizardNode: no task_id, returning empty")
            return ("",)

        logger.info("SeedanceWizardNode: waiting for task %s", task_id)

        client = _get_client()

        # Poll synchronously (blocks the prompt queue; video gen is the
        # final step so this is acceptable)
        max_wait = 600  # 10 minutes max
        poll_interval = 3  # seconds
        elapsed = 0

        while elapsed < max_wait:
            result, status = client.forward("GET", f"/api/video/{task_id}/status")
            task_status = result.get("status", "unknown")
            progress = result.get("progress", 0)

            logger.debug("Task %s status: %s (%d%%)", task_id, task_status, progress)

            if task_status == "completed":
                video_url = result.get("video_url", "")
                if not video_url:
                    # Try the result endpoint
                    res2, _ = client.forward("GET", f"/api/video/{task_id}/result")
                    video_url = res2.get("video_url", "")

                if video_url:
                    local_path = self._download_video(video_url, task_id)
                    _wizard_state["video_path"] = local_path
                    _wizard_state["video_url"] = video_url
                    _wizard_state["task_status"] = "completed"

                    # Push completion via WebSocket
                    try:
                        from server import PromptServer
                        PromptServer.instance.send_sync("seedance_video_complete", {
                            "task_id": task_id,
                            "video_url": video_url,
                            "local_path": local_path,
                            "estimated_cost_fen": result.get("estimated_cost_fen"),
                            "actual_cost_fen": result.get("actual_cost_fen"),
                            "message": "Video ready!",
                        })
                    except Exception:
                        pass

                    return (local_path,)
                else:
                    _wizard_state["last_error"] = "No video URL in completed response"
                    return ("",)

            elif task_status == "failed":
                error_msg = result.get("error", result.get("message", "Unknown error"))
                _wizard_state["last_error"] = error_msg
                _wizard_state["task_status"] = "failed"

                try:
                    from server import PromptServer
                    PromptServer.instance.send_sync("seedance_error", {
                        "code": "GENERATION_FAILED",
                        "message": error_msg,
                        "task_id": task_id,
                    })
                except Exception:
                    pass

                return ("",)

            # Still processing — wait and retry
            time.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout
        _wizard_state["last_error"] = f"Video generation timed out after {max_wait}s"
        _wizard_state["task_status"] = "timeout"

        try:
            from server import PromptServer
            PromptServer.instance.send_sync("seedance_error", {
                "code": "TIMEOUT",
                "message": _wizard_state["last_error"],
                "task_id": task_id,
            })
        except Exception:
            pass

        return ("",)

    def _download_video(self, video_url: str, task_id: str) -> str:
        """Download a video from the given URL to ComfyUI's output directory."""
        base = _get_comfyui_base_path()
        output_dir = os.path.join(base, "output", "seedance")
        os.makedirs(output_dir, exist_ok=True)

        filename = f"seedance_{task_id[:16]}.mp4"
        local_path = os.path.join(output_dir, filename)

        logger.info("Downloading video from %s to %s", video_url, local_path)

        try:
            urllib.request.urlretrieve(video_url, local_path)
        except Exception as e:
            logger.error("Failed to download video: %s", e)
            # Try with a timeout-aware approach
            req = urllib.request.Request(video_url)
            with urllib.request.urlopen(req, timeout=300) as resp:
                with open(local_path, "wb") as f:
                    f.write(resp.read())

        logger.info("Video saved to %s", local_path)
        return local_path


# ──────────────────────────────────────────────
# ComfyUI Node: SeedanceApiKeyNode (optional)
# ──────────────────────────────────────────────

class SeedanceApiKeyNode:
    """
    Optional standalone node for providing an API key as a workflow input.

    Advanced users can wire this node's output into the SeedanceWizardNode's
    api_key input. Most users will configure the key through the wizard UI
    (which writes to the config file) instead.
    """

    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("api_key",)
    FUNCTION = "load_key"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Seedance API Key (sk-seed-...)"
                }),
            }
        }

    def load_key(self, api_key: str = "") -> tuple:
        """Return the provided API key string."""
        return (api_key,)


# ──────────────────────────────────────────────
# ComfyUI mapping exports
# ──────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "SeedanceWizardNode": SeedanceWizardNode,
    "SeedanceApiKeyNode": SeedanceApiKeyNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeedanceWizardNode": "Seedance Wizard",
    "SeedanceApiKeyNode": "Seedance API Key",
}
