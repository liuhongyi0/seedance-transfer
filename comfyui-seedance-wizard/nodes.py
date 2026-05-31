"""
nodes.py — ComfyUI Seedance Wizard core module

Contains:
  - SeedanceWizardNode: main node with dual-mode support
    * Sidebar mode — interactive wizard via HTML panel
    * Pipeline mode — accepts IMAGE/STRING inputs from upstream nodes
  - SeedanceApiKeyNode: optional API key configuration node
  - SeedanceImageInputNode: bridge node for pipeline image input
  - PromptServer route handlers: forward requests to FastAPI backend
  - Configuration management: read/write seedance_config.json
  - API client: authenticated HTTP forwarding to backend

All routes are prefixed with /seedance. The HTML wizard panel fetches
to localhost:8188/seedance/*, and this module attaches the Bearer token
before forwarding to the backend.

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
import io
import base64
from typing import Optional, Dict, Any

import numpy as np
from PIL import Image

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
# IMAGE tensor conversion helpers
# ──────────────────────────────────────────────

def tensor_to_base64(img_tensor) -> str:
    """Convert ComfyUI IMAGE tensor [B,H,W,C] float32 0~1 → base64 PNG string.

    Returns a data URI string: data:image/png;base64,...
    """
    # Take first batch item: [1, H, W, C] → [H, W, C]
    arr = img_tensor[0].cpu().numpy()
    arr = (arr * 255).clip(0, 255).astype(np.uint8)
    pil_img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def url_to_tensor(image_url: str) -> Optional[Any]:
    """Download an image URL and convert to ComfyUI IMAGE tensor [1,H,W,C].

    Returns None on failure.
    """
    import torch

    try:
        req = urllib.request.Request(image_url, headers={
            "User-Agent": "ComfyUI-Seedance/1.0"
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        pil_img = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.array(pil_img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)  # [1, H, W, C]
        return tensor
    except Exception as e:
        logger.error("Failed to download/convert preview image: %s", e)
        return None


def tensor_to_pil(img_tensor) -> Image.Image:
    """Convert ComfyUI IMAGE tensor [B,H,W,C] → PIL Image (first batch item)."""
    arr = img_tensor[0].cpu().numpy()
    arr = (arr * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


# ──────────────────────────────────────────────
# Configuration management
# ──────────────────────────────────────────────

DEFAULT_CONFIG = {
    "api_key": "",
    "backend_url": "http://localhost:8000",
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
    """Synchronous HTTP client that forwards requests to the backend
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
            body = await request.json()
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

            # Check for error responses (backend uses "detail" for HTTPException, "error" for others)
            err_code = result.get("code") or result.get("error") or ""
            err_msg = result.get("message") or result.get("detail") or ""
            if "BALANCE" in str(err_code).upper() or "402" in str(err_msg):
                server.send_sync("seedance_error", {
                    "code": "INSUFFICIENT_BALANCE",
                    "message": err_msg or "Insufficient balance",
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
    Seedance Wizard — dual-mode AI video generation node.

    **Sidebar mode** (interactive):
      Open the Seedance Wizard tab, upload an image, describe your idea,
      tune parameters, and generate. The 'trigger' input polls for results.

    **Pipeline mode** (node graph):
      Connect IMAGE from LoadImage (or any image-output node) and STRING
      prompts from text nodes directly. The node handles the full pipeline:
      analyze → preview → generate → download.

      Outputs:
        - video_path: local file path to the generated MP4
        - preview_thumbnail: preview image as ComfyUI IMAGE tensor
        - final_prompt: the composed English prompt sent to the video model
    """

    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("video_path", "preview_thumbnail", "final_prompt")
    OUTPUT_NODE = True
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("INT", {
                    "default": 0, "min": 0, "max": 999999,
                    "tooltip": "Sidebar mode: increment to poll sidebar-submitted task. Starts at 1."
                }),
            },
            "optional": {
                # ── Pipeline mode inputs ──
                "image": ("IMAGE", {
                    "tooltip": "Pipeline mode: connect LoadImage or any image-output node here."
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "Pipeline mode: optional! AI auto-generates prompt/style/everything from image. Add 1-2 sentences to guide direction."
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {
                    "default": "16:9",
                    "tooltip": "Video aspect ratio."
                }),
                "style": (["cinematic", "commercial", "documentary", "social_media", "artistic"], {
                    "default": "cinematic",
                    "tooltip": "Visual style category."
                }),
                "mood": (["energetic", "serene", "mysterious", "joyful", "dramatic"], {
                    "default": "dramatic",
                    "tooltip": "Emotional atmosphere."
                }),
                "camera": (["close_up", "medium_shot", "wide_shot", "aerial_view", "low_angle"], {
                    "default": "medium_shot",
                    "tooltip": "Camera shot type."
                }),
                "lighting": (["bright_daylight", "golden_hour", "soft_diffused", "dramatic_shadows", "neon_night"], {
                    "default": "soft_diffused",
                    "tooltip": "Lighting setup."
                }),
                "color_tone": (["warm", "cool", "vibrant", "muted", "monochrome"], {
                    "default": "warm",
                    "tooltip": "Color palette."
                }),
                "motion_intensity": ("FLOAT", {
                    "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "How much camera movement / action."
                }),
                "seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "tooltip": "Random seed (0 = random)."
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Override API key (leave empty to use config file)."
                }),
                "model_key": (["seedance-1.5", "seedance-2.0", "kling-o3"], {
                    "default": "seedance-1.5",
                    "tooltip": "seedance-1.5=Best Value, seedance-2.0=Flagship, kling-o3=Cinematic"
                }),
            }
        }

    def process(self, trigger: int = 0, image=None, prompt: str = "",
                aspect_ratio: str = "16:9", style: str = "cinematic",
                mood: str = "dramatic", camera: str = "medium_shot",
                lighting: str = "soft_diffused", color_tone: str = "warm",
                motion_intensity: float = 0.5, seed: int = 0,
                api_key: str = "", model_key: str = "seedance-1.5", **kwargs):
        """
        Main entry point. Detects sidebar vs pipeline mode automatically.
        """
        # Detect mode: pipeline mode when image tensor has content
        is_pipeline = (image is not None and hasattr(image, "shape")
                       and len(image.shape) >= 3 and image.shape[0] > 0)

        if is_pipeline:
            _reset_wizard_state()
            return self._pipeline_mode(
                image=image, prompt=prompt, aspect_ratio=aspect_ratio,
                style=style, mood=mood, camera=camera, lighting=lighting,
                color_tone=color_tone, motion_intensity=motion_intensity,
                seed=seed, api_key=api_key, model_key=model_key
            )
        else:
            return self._sidebar_mode(trigger, api_key)

    # ── Sidebar Mode ──────────────────────────────────────────────────

    def _sidebar_mode(self, trigger: int, api_key: str = "") -> tuple:
        """Poll for video completion from sidebar wizard submission."""
        if trigger < 1:
            return ("", None, "")

        task_id = _wizard_state.get("current_task_id")
        if not task_id:
            logger.debug("SeedanceWizardNode (sidebar): no task_id, returning empty")
            return ("", None, "")

        logger.info("SeedanceWizardNode (sidebar): waiting for task %s", task_id)

        client = _get_client()

        max_wait = 600
        poll_interval = 3
        elapsed = 0

        while elapsed < max_wait:
            result, status = client.forward("GET", f"/api/video/{task_id}/status")
            task_status = result.get("status", "unknown")
            progress = result.get("progress", 0)

            logger.debug("Task %s status: %s (%d%%)", task_id, task_status, progress)

            # Check for connection / backend errors
            if status >= 500 or result.get("error"):
                err_msg = result.get("error", f"Backend error (HTTP {status})")
                _wizard_state["last_error"] = err_msg
                _wizard_state["task_status"] = "failed"
                self._push_ws("seedance_error", {"code": "BACKEND_ERROR", "message": err_msg, "task_id": task_id})
                return ("", None, "")

            if task_status == "completed":
                video_url = result.get("video_url", "")
                if not video_url:
                    res2, _ = client.forward("GET", f"/api/video/{task_id}/result")
                    video_url = res2.get("video_url", "")

                if video_url:
                    local_path = self._download_video(video_url, task_id)
                    _wizard_state["video_path"] = local_path
                    _wizard_state["video_url"] = video_url
                    _wizard_state["task_status"] = "completed"

                    self._push_ws("seedance_video_complete", {
                        "task_id": task_id,
                        "video_url": video_url,
                        "local_path": local_path,
                        "message": "Video ready!",
                    })

                    return (local_path, None, "")

                _wizard_state["last_error"] = "No video URL in completed response"
                return ("", None, "")

            elif task_status == "failed":
                error_msg = result.get("error", result.get("message", "Unknown error"))
                _wizard_state["last_error"] = error_msg
                _wizard_state["task_status"] = "failed"
                self._push_ws("seedance_error", {
                    "code": "GENERATION_FAILED",
                    "message": error_msg,
                    "task_id": task_id,
                })
                return ("", None, "")

            time.sleep(poll_interval)
            elapsed += poll_interval

        _wizard_state["last_error"] = f"Video generation timed out after {max_wait}s"
        _wizard_state["task_status"] = "timeout"
        self._push_ws("seedance_error", {
            "code": "TIMEOUT",
            "message": _wizard_state["last_error"],
            "task_id": task_id,
        })
        return ("", None, "")

    # ── Pipeline Mode ─────────────────────────────────────────────────

    def _pipeline_mode(self, image, prompt: str, aspect_ratio: str,
                       style: str, mood: str, camera: str, lighting: str,
                       color_tone: str, motion_intensity: float, seed: int,
                       api_key: str = "", model_key: str = "seedance-1.5") -> tuple:
        """Full auto pipeline: analyze → preview → generate → download."""
        import torch

        # Check API Key early
        effective_key = api_key if api_key else get_api_key()
        if not effective_key:
            err_msg = "No API Key configured. Open Seedance Wizard sidebar → Settings → Register/Login to get one."
            logger.error(err_msg)
            self._push_ws("seedance_error", {"code": "NO_API_KEY", "message": err_msg})
            raise RuntimeError(err_msg)

        img_b64 = tensor_to_base64(image)

        self._push_ws("seedance_pipeline_progress", {
            "stage": "analyze",
            "progress": 5,
            "message": "Analyzing image with AI...",
        })

        # Step 1: Analyze
        analyze_result, analyze_status = self._call_analyze(img_b64, prompt, aspect_ratio)

        if not analyze_result.get("success") and analyze_status >= 400:
            logger.error("Pipeline analyze failed: %s", analyze_result)
            self._push_ws("seedance_error", {
                "code": "ANALYZE_FAILED",
                "message": analyze_result.get("detail", str(analyze_result)),
            })
            return ("", None, "")

        final_prompt = analyze_result.get("prompt_en", prompt)
        ai_style = analyze_result.get("style", style)
        ai_mood = analyze_result.get("mood", mood)
        ai_camera = analyze_result.get("camera", camera)
        ai_color = analyze_result.get("color_palette", color_tone)
        ai_lighting = analyze_result.get("lighting", lighting)

        self._push_ws("seedance_pipeline_progress", {
            "stage": "preview",
            "progress": 25,
            "message": "Generating preview image...",
            "analyze_result": {
                "style": ai_style, "mood": ai_mood, "camera": ai_camera,
                "color_palette": ai_color, "lighting": ai_lighting,
                "prompt_en": final_prompt,
            }
        })

        # Step 2: Preview (Flux / Wanx)
        preview_result, _ = self._call_preview(
            style=ai_style, mood=ai_mood, color_palette=ai_color,
            camera=ai_camera, prompt_en=final_prompt, aspect_ratio=aspect_ratio,
            lighting=ai_lighting
        )

        preview_url = preview_result.get("preview_url", "")

        self._push_ws("seedance_pipeline_progress", {
            "stage": "generate",
            "progress": 45,
            "message": "Submitting video generation task...",
        })

        # Step 3: Generate video
        gen_result, gen_status = self._call_generate_video(
            prompt_en=final_prompt, aspect_ratio=aspect_ratio,
            image_b64=img_b64, model_key=model_key
        )

        task_id = gen_result.get("task_id", "")
        if not task_id:
            logger.error("Pipeline generate failed: %s", gen_result)
            self._push_ws("seedance_error", {
                "code": "GENERATE_FAILED",
                "message": gen_result.get("detail", "No task_id returned"),
            })
            # Return preview at least
            preview_tensor = url_to_tensor(preview_url) if preview_url else None
            return ("", preview_tensor, final_prompt)

        _wizard_state["current_task_id"] = task_id

        # Step 4: Poll for completion
        client = _get_client()
        max_wait = 600
        poll_interval = 3
        elapsed = 0

        while elapsed < max_wait:
            result, status = client.forward("GET", f"/api/video/{task_id}/status")
            task_status = result.get("status", "unknown")
            progress = result.get("progress", 0)
            err_msg = result.get("error", "")

            self._push_ws("seedance_pipeline_progress", {
                "stage": "generating",
                "progress": 45 + int(progress * 0.5),
                "message": f"Generating video: {progress}%",
                "task_id": task_id,
                "task_status": task_status,
            })

            # Early exit on connection / backend / balance errors
            if status >= 500 or err_msg:
                self._push_ws("seedance_error", {"code": "BACKEND_ERROR", "message": err_msg or f"HTTP {status}", "task_id": task_id})
                preview_tensor = url_to_tensor(preview_url) if preview_url else None
                return ("", preview_tensor, final_prompt)

            if task_status == "completed":
                video_url = result.get("video_url", "")
                if not video_url:
                    res2, _ = client.forward("GET", f"/api/video/{task_id}/result")
                    video_url = res2.get("video_url", "")

                if video_url:
                    local_path = self._download_video(video_url, task_id)
                    _wizard_state["video_path"] = local_path
                    _wizard_state["video_url"] = video_url
                    _wizard_state["task_status"] = "completed"

                    preview_tensor = url_to_tensor(preview_url) if preview_url else None

                    self._push_ws("seedance_video_complete", {
                        "task_id": task_id,
                        "video_url": video_url,
                        "local_path": local_path,
                        "preview_url": preview_url,
                        "message": "Pipeline complete!",
                    })

                    return (local_path, preview_tensor, final_prompt)

                _wizard_state["last_error"] = "No video URL in completed response"
                return ("", None, final_prompt)

            elif task_status == "failed":
                error_msg = result.get("error", "Unknown error")
                _wizard_state["last_error"] = error_msg
                _wizard_state["task_status"] = "failed"
                self._push_ws("seedance_error", {
                    "code": "GENERATION_FAILED",
                    "message": error_msg,
                    "task_id": task_id,
                })
                return ("", None, final_prompt)

            time.sleep(poll_interval)
            elapsed += poll_interval

        _wizard_state["last_error"] = f"Video generation timed out after {max_wait}s"
        _wizard_state["task_status"] = "timeout"
        self._push_ws("seedance_error", {
            "code": "TIMEOUT",
            "message": _wizard_state["last_error"],
            "task_id": task_id,
        })
        return ("", None, final_prompt)

    # ── API call helpers ──────────────────────────────────────────────

    def _call_analyze(self, img_b64: str, prompt: str, aspect_ratio: str) -> tuple:
        """Call /api/wizard/analyze. Returns (result_dict, status_code)."""
        client = _get_client()
        return client.forward("POST", "/api/wizard/analyze", {
            "image_b64": img_b64,
            "idea_text": prompt,
            "aspect_ratio": aspect_ratio,
        })

    def _call_preview(self, style: str, mood: str, color_palette: str,
                      camera: str, prompt_en: str, aspect_ratio: str,
                      lighting: str = "soft_diffused") -> tuple:
        """Call /api/wizard/preview. Returns (result_dict, status_code)."""
        client = _get_client()
        return client.forward("POST", "/api/wizard/preview", {
            "style": style,
            "mood": mood,
            "color_palette": color_palette,
            "camera": camera,
            "lighting": lighting,
            "prompt_en": prompt_en,
            "aspect_ratio": aspect_ratio,
        })

    def _call_generate_video(self, prompt_en: str, aspect_ratio: str,
                             image_b64: str = "", duration: int = 5,
                             resolution: str = "720p",
                             model_key: str = "seedance-1.5") -> tuple:
        """Call /api/video/generate. Returns (result_dict, status_code)."""
        client = _get_client()
        body = {
            "prompt_en": prompt_en,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "image_b64": image_b64 if image_b64 else None,
            "model_key": model_key,
        }
        return client.forward("POST", "/api/video/generate", body)

    # ── Shared helpers ────────────────────────────────────────────────

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
            logger.error("urlretrieve failed, trying manual download: %s", e)
            try:
                req = urllib.request.Request(video_url, headers={
                    "User-Agent": "ComfyUI-Seedance/1.0"
                })
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(local_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            except OSError as oe:
                logger.error("Download/save failed: %s", oe)
                return ""

        return local_path  # success path for both urlretrieve and manual download

    def _push_ws(self, event: str, data: dict):
        """Push a WebSocket event to the ComfyUI frontend (best-effort)."""
        try:
            from server import PromptServer
            PromptServer.instance.send_sync(event, data)
        except Exception:
            pass


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
# ComfyUI Node: SeedanceImageInputNode (pipeline helper)
# ──────────────────────────────────────────────

class SeedanceImageInputNode:
    """
    Pipeline helper: explicitly marks an IMAGE input for Seedance Wizard.

    This is a convenience node. You can also connect any image-output node
    (LoadImage, VAE Decode, etc.) directly to SeedanceWizardNode's 'image'
    input. This node exists so the workflow is self-documenting.

    Connect the output of LoadImage → SeedanceImageInputNode →
    SeedanceWizardNode for a clearly readable pipeline.
    """

    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "passthrough"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "Connect a LoadImage or any image-output node here."
                }),
            }
        }

    def passthrough(self, image):
        """Pass the image tensor through unchanged."""
        return (image,)


# ──────────────────────────────────────────────
# ComfyUI mapping exports
# ──────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "SeedanceWizardNode": SeedanceWizardNode,
    "SeedanceApiKeyNode": SeedanceApiKeyNode,
    "SeedanceImageInputNode": SeedanceImageInputNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeedanceWizardNode": "Seedance Wizard",
    "SeedanceApiKeyNode": "Seedance API Key",
    "SeedanceImageInputNode": "Seedance Image Input",
}
