# Seedance Wizard — ComfyUI Custom Node

AI-powered video creation wizard for [Seedance 2.0](https://seedance.com), built as a ComfyUI custom node.

## Features

- **4-step guided wizard** — Upload image → AI analysis (Qwen VL + DeepSeek) → Parameter tuning → Video generation
- **Structured parameter panel** — 5 categorical dropdowns (style/lighting/shot/mood/color) + 4 numeric sliders with 600ms debounced live preview
- **Flux preview images** — Generate keyframe previews via fal.ai before committing to video (requires `FAL_KEY`)
- **Graceful degradation** — If Flux is unavailable, original uploaded image is shown as reference
- **Seedance 2.0 T2V + I2V** — Text-to-video and image-to-video via muapi.ai
- **WebSocket push** — Real-time progress updates back to the sidebar UI

## Quick Start

### 1. Backend Setup (required)

```bash
cd seedance-transfer/backend
cp .env.example .env   # or edit .env directly
# Fill in: DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, MUAPI_KEY, FAL_KEY (optional)
npm run dev
```

### 2. Install Node

```bash
cd ComfyUI/custom_nodes
ln -s /path/to/seedance-transfer/comfyui-seedance-wizard ./comfyui-seedance-wizard
# Or clone directly:
# git clone https://github.com/your-org/comfyui-seedance-wizard.git
```

No extra Python packages required — uses only stdlib (`urllib`, `json`).

### 3. Configure API Key

Start ComfyUI, open the **Seedance** sidebar tab, click ⚙ and set:
- **API Key**: your `sk-seed-...` key (create one at `POST /api/keys`)
- **Backend URL**: `http://localhost:3000`

Or create `ComfyUI/user/default/seedance_config.json` directly:

```json
{
  "api_key": "sk-seed-...",
  "backend_url": "http://localhost:3000",
  "language": "zh"
}
```

### 4. Verify Routes (H-3 test)

```bash
# ComfyUI must be running on port 8188
curl http://localhost:8188/seedance/settings
# → {"api_key_configured": true, "backend_url": "http://localhost:3000", ...}

curl http://localhost:8188/seedance/balance
# → {"amount_fen": ..., "amount_yuan": ..., "currency": "CNY"}
```

## Wizard Flow

```
Step 1  →  Upload image + describe idea + pick ratio
Step 2  →  AI analyzing (Qwen VL → DeepSeek → Flux preview)
Step 3  →  Tune 9 parameters, preview updates every 600ms
Step 4  →  Video generation progress + download link
```

## PromptServer Routes

| Method | Route | Backend |
|--------|-------|---------|
| POST | `/seedance/wizard/analyze` | `/api/wizard/analyze` |
| POST | `/seedance/wizard/preview` | `/api/wizard/preview` |
| POST | `/seedance/video/generate` | `/api/video/generate` |
| GET  | `/seedance/video/status?task_id=` | `/api/video/{id}/status` |
| GET  | `/seedance/video/result?task_id=` | `/api/video/{id}/result` |
| GET  | `/seedance/balance` | `/api/balance` |
| GET  | `/seedance/settings` | local config |
| POST | `/seedance/settings` | local config |

## Nodes

### SeedanceWizardNode

Main output node. Polls for video completion when triggered.

| Input | Type | Description |
|-------|------|-------------|
| `trigger` | INT | Increment to start polling |
| `api_key` | STRING (opt) | Override API key from config |

**Output**: `video_path` (STRING) — local path to downloaded MP4

### SeedanceApiKeyNode

Optional: provide API key as a workflow wire instead of config file.

## Architecture

```
wizard.html  ←postMessage→  main.js  ←fetch→  nodes.py routes
                              main.js  ←WebSocket←  nodes.py
nodes.py  ←HTTP→  Node.js backend  ←API→  DeepSeek / Qwen VL / fal.ai / Seedance
```

## License

MIT — Copyright (c) 2025 Seedance Wizard Contributors
