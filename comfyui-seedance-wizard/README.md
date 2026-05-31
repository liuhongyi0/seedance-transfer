# Seedance Wizard — ComfyUI Custom Node

AI video creation directly inside ComfyUI. Upload an image, describe your vision, and generate a complete video — with AI script writing, preview images, video drafts, music, and final rendering via 18 AI models.

## Features

- **Dual mode** — Sidebar wizard (interactive) + Pipeline node (connect images/prompts from other nodes)
- **AI analysis** — Analyzes your reference image with vision models, auto-generates style/mood/camera/prompt suggestions
- **18 AI models** — Seedance 2.0, Kling O3, Veo 3.1, Sora 2, Wan 2.7, and more — all included
- **Live preview** — Generate keyframe images before committing to video
- **Background music** — AI-generated soundtrack via Suno V5
- **WebSocket push** — Real-time progress: analyze → preview → generating → complete
- **Credit system** — Pay-as-you-go. Credits never expire. No subscription.

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/liuhongyi0/comfyui-seedance-wizard.git
# No extra Python packages required beyond numpy + Pillow
```

## Configure

1. Open ComfyUI → Seedance sidebar tab → ⚙ Settings
2. Set **Backend URL**: `https://see4dance.com`
3. Register at [see4dance.com](https://see4dance.com) → get your API Key (`sk-seed-...`)

Or create `ComfyUI/user/default/seedance_config.json`:

```json
{
  "api_key": "sk-seed-xxxx",
  "backend_url": "https://see4dance.com",
  "language": "en"
}
```

## Nodes

### SeedanceWizardNode

Main output node. Sidebar mode polls for results; Pipeline mode runs the full analyze → preview → generate pipeline automatically.

| Input | Type | Description |
|-------|------|-------------|
| trigger | INT | Sidebar: increment to start polling |
| image | IMAGE | Pipeline: connect LoadImage or any image node |
| prompt | STRING | Pipeline: optional creative direction |
| model_key | select | seedance-1.5 / seedance-2.0 / veo3.1-fast / kling-o3 / ... |
| aspect_ratio | select | 16:9 / 9:16 / 1:1 |
| style / mood / camera / lighting / color_tone | select | AI will auto-fill these from image analysis |

**Outputs**: `video_path`, `preview_thumbnail`, `final_prompt`

### SeedanceApiKeyNode

Optional: wire a key into the workflow instead of using config file.

### SeedanceImageInputNode

Pipeline helper: makes image flow explicit in the node graph.

## Backend

This node requires a Seedance Studio backend. The public instance runs at `https://see4dance.com`.

[Self-hosting instructions →](https://github.com/liuhongyi0/seedance-transfer)

## License

MIT — Copyright (c) 2025-2026 Seedance Wizard Contributors
