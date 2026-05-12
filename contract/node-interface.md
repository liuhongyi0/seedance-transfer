# ComfyUI 节点接口契约

> 约定 ComfyUI Python 节点、HTML 向导面板、Node.js 后端三者之间的所有通信接口。
> 开发 Agent 1（ComfyUI 节点）和 Agent 2（Node.js 后端）都必须严格遵守本文档。

---

## 1. 整体通信拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                    用户本地（ComfyUI 环境）                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  HTML 向导面板（浏览器，运行在 localhost:8188）          │    │
│  │                                                     │    │
│  │  ① 向导 UI      ② CSS 滤镜引擎    ③ 状态显示         │    │
│  └──────┬──────────────────────┬──────────────────────┘    │
│         │                      │                            │
│         │ A. fetch POST/GET     │ B. WebSocket 监听          │
│         │ localhost:8188/       │ ws://localhost:8188/ws     │
│         │ seedance/wizard/*     │                            │
│         ▼                      │                            │
│  ┌──────────────────────┐      │                            │
│  │  ComfyUI Python 节点  │◄─────┘                            │
│  │  (PromptServer 路由)  │                                   │
│  └──────┬───────────────┘                                   │
│         │                                                    │
│         │ C. HTTPS（带 Bearer token）                         │
│         ▼                                                    │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  Node.js 后端             │
│  http://api.seedance.cn  │
│  (或 localhost:3000 开发) │
└──────────────────────────┘
          │
          ├──→ DeepSeek API（导演）
          ├──→ DashScope API（Qwen VL 看图）
          ├──→ muapi.ai（Flux 预览 + Seedance 出片）
          └──→ 数据库（Key 管理 + 余额）
```

**关键约定**：
- HTML 向导面板永远**不直接**调用 Node.js 后端，所有请求先到 `localhost:8188/seedance/wizard/*`，由 Python 节点转发（附加 API Key Header）。
- 这样设计的原因：① API Key 不暴露在浏览器 JS 中；② Python 节点可以拦截错误、统一处理。

---

## 2. Python 节点注册的 PromptServer 路由（通道 A）

Python 节点在 `nodes.py` 中通过 `PromptServer.instance.routes` 注册以下路由。

### 2.1 向导会话管理

#### `POST /seedance/wizard/start`
HTML 向导发起新会话。Python 节点附加 API Key 后转发到 Node.js 后端 `/api/wizard/start`。

**Request（来自 HTML 向导）**：
```json
{
  "intent": "温馨电商广告，15秒",
  "image_b64": "data:image/jpeg;base64,...",   // 可选
  "language": "zh"
}
```

**Python 节点行为**：
1. 从 ComfyUI 设置读取 `seedance_api_key`
2. 附加 `Authorization: Bearer <key>` Header
3. 转发到 `POST {BACKEND_URL}/api/wizard/start`
4. 原样返回 Node.js 的响应给 HTML 向导

**Response（透传 Node.js 响应）**：
```json
{
  "session_id": "uuid-xxxx",
  "director_message": "我看到一个白色护肤品瓶...",
  "suggested_options": [
    { "label": "温馨电商广告", "value": "warm_ecommerce" },
    { "label": "品牌宣传片", "value": "brand_promo" }
  ],
  "current_prompt": "A white skincare bottle on wooden desk...",
  "image_analyzed": true
}
```

---

#### `POST /seedance/wizard/message`
用户发送反馈，继续对话。

**Request**：
```json
{
  "session_id": "uuid-xxxx",
  "message": "光线再暖一点，背景虚化",
  "css_params": {
    "warmth": 0.3,
    "brightness": 0.1,
    "blur": 0.4,
    "contrast": 0.0,
    "saturation": 0.2
  }
}
```

**Python 节点行为**：附加 Bearer token，转发到 `/api/wizard/message`，原样返回。

---

#### `POST /seedance/wizard/preview`
请求 Flux 预览图。

**Request**：
```json
{
  "session_id": "uuid-xxxx",
  "aspect_ratio": "16:9",
  "prompt_override": null   // 若用户手动编辑了 Prompt
}
```

**Python 节点行为**：附加 Bearer token，转发到 `/api/wizard/preview`，原样返回。

**Response 示例**：
```json
{
  "preview_url": "https://cdn.seedance.cn/preview/abc123.jpg",
  "cost_fen": 1,
  "balance_after": 6799
}
```

---

### 2.2 视频生成

#### `POST /seedance/video/generate`
用户点击"开始生成视频"。

**Request（来自 HTML 向导）**：
```json
{
  "session_id": "uuid-xxxx",
  "mode": "text_to_video",
  "image_b64": null,
  "aspect_ratio": "16:9",
  "duration": 5,
  "quality": "high",
  "prompt_override": null
}
```

**Python 节点行为**：
1. 转发到 `/api/video/generate`，获取 `task_id`
2. **将 `task_id` 存入节点内部状态**（供后续 ComfyUI 执行流程使用）
3. 返回 task_id 给 HTML 向导（触发前端轮询）
4. 同时触发 ComfyUI 内部的视频等待流程（见 2.3）

**Response**：
```json
{
  "task_id": "muapi-task-xyz",
  "estimated_cost_fen": 315,
  "estimated_seconds": 90,
  "balance_after": 6484
}
```

---

#### `GET /seedance/video/status?task_id=<id>`
HTML 向导轮询生成进度（每 3 秒调一次）。

**Python 节点行为**：转发到 `/api/video/{taskId}/status`，原样返回。

**Response**：
```json
{
  "task_id": "muapi-task-xyz",
  "status": "processing",    // queued | processing | completed | failed
  "progress": 45
}
```

当 `status == "completed"` 时，Python 节点**主动通过 WebSocket 推送完成事件**（见通道 B）。

---

#### `GET /seedance/video/result?task_id=<id>`
获取已完成任务的视频信息。

**Python 节点行为**：转发到 `/api/video/{taskId}/result`，原样返回。

---

### 2.3 工具路由

#### `GET /seedance/settings`
HTML 向导读取当前设置（是否已配置 API Key、后端地址等）。

**Response**：
```json
{
  "api_key_configured": true,
  "api_key_prefix": "sk-seed-ab12",
  "backend_url": "https://api.seedance.cn",
  "language": "zh"
}
```

#### `POST /seedance/settings`
保存设置（从向导 UI 配置 API Key 时调用）。

**Request**：
```json
{
  "api_key": "sk-seed-ab12cdef...",
  "backend_url": "https://api.seedance.cn"
}
```
Python 节点将 API Key 存入 ComfyUI 的用户配置文件（`config.json`），**不存入向导前端**。

#### `POST /seedance/estimate`
出片费用预估（无需扣费）。转发到 `/api/estimate`。

---

## 3. WebSocket 事件（通道 B）

Python 节点使用 `PromptServer.instance.send_sync(event_name, data)` 推送事件。
HTML 向导通过 `api.addEventListener(event_name, handler)` 监听。

**命名空间约定**：所有事件名以 `seedance_` 开头，避免与 ComfyUI 内置事件冲突。

### 3.1 视频生成进度

**事件名**：`seedance_video_progress`

```json
{
  "task_id": "muapi-task-xyz",
  "status": "processing",
  "progress": 67,
  "message": "生成中..."
}
```

Python 节点在以下时机推送：
- 视频任务提交成功后（progress: 0）
- 每次轮询到进度更新时（Node.js 后端后台轮询，通过 WebSocket 推给前端）
- 任务完成时（progress: 100）
- 任务失败时

### 3.2 视频生成完成

**事件名**：`seedance_video_complete`

```json
{
  "task_id": "muapi-task-xyz",
  "video_url": "https://cdn.seedance.cn/output/abc123.mp4",
  "actual_cost_fen": 315,
  "balance_after": 6484,
  "duration_ms": 73450
}
```

HTML 向导收到此事件后：显示"生成完成"提示，更新余额显示。

**Python 节点收到来自后端的 complete 通知后还需要**：
1. 下载视频到 ComfyUI 的 `output/` 目录
2. 解帧（或直接输出视频文件路径）
3. 通过 ComfyUI 正常的执行结果机制把视频传给后续节点

### 3.3 错误事件

**事件名**：`seedance_error`

```json
{
  "code": "INSUFFICIENT_BALANCE",
  "message": "余额不足，请充值",
  "task_id": "muapi-task-xyz"   // 若错误发生在生成过程中
}
```

---

## 4. ComfyUI 节点定义

### 4.1 SeedanceWizardNode（主节点）

```python
class SeedanceWizardNode:
    """
    HTML 向导的 Python 宿主节点。
    - 持有 API Key 和 session 状态
    - 注册 PromptServer 路由
    - 触发视频生成并等待结果
    - 输出视频到 ComfyUI 画布
    """
    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("IMAGE", "STRING")     # 视频首帧预览图 + 视频文件路径
    RETURN_NAMES = ("preview_frame", "video_path")
    OUTPUT_NODE = True
    FUNCTION = "wait_for_video"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("INT", {"default": 0}),      # 由向导前端触发，每次生成自增
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),  # 可从节点 widget 输入，优先级低于配置文件
            }
        }

    def wait_for_video(self, trigger, api_key=""):
        # 从内部状态获取当前 task_id
        # 轮询直到完成
        # 下载视频，解首帧
        # 返回 (首帧 tensor, 视频路径)
        ...
```

**节点在 ComfyUI 中的角色**：
- 用户通常把它放在画布右侧作为终端节点
- 向导 HTML 是主要交互界面；这个节点是视频输出的载体
- 节点的 `trigger` widget 数字每次出片自增（由向导 JS 通过 `app.graph` 更新）

### 4.2 SeedanceApiKeyNode（辅助节点，可选）

```python
class SeedanceApiKeyNode:
    """
    独立的 API Key 配置节点（给高级用户）。
    普通用户直接在向导 HTML 里配置，不需要这个节点。
    """
    CATEGORY = "Seedance Wizard"
    RETURN_TYPES = ("SEEDANCE_KEY",)
    RETURN_NAMES = ("api_key",)
    FUNCTION = "load_key"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": "sk-seed-..."})
            }
        }
```

---

## 5. WEB_DIRECTORY 文件结构

```
comfyui-seedance-wizard/
├── __init__.py
│     WEB_DIRECTORY = "./web"
│
├── web/
│   ├── main.js              # 【ComfyUI 自动加载】注册 sidebarTab + 监听 WebSocket
│   ├── wizard.html          # 向导主界面（通过 iframe 加载）
│   ├── wizard.css           # 向导样式（暗色主题，匹配 ComfyUI）
│   └── filter-preview.js    # CSS 滤镜引擎（被 wizard.html 引用）
```

### main.js 关键结构

```javascript
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
  name: "seedance.wizard",

  async setup() {
    // 注册侧边栏面板
    app.extensionManager.registerSidebarTab({
      id: "seedance.wizard",
      icon: "pi pi-video",
      title: "Seedance 向导",
      tooltip: "AI 视频创作向导",
      type: "custom",
      render: (el) => {
        const iframe = document.createElement("iframe");
        iframe.src = "/extensions/comfyui-seedance-wizard/wizard.html";
        iframe.style.cssText = "width:100%;height:100%;border:none;";
        el.appendChild(iframe);
      }
    });

    // 监听后端推送的视频进度事件
    api.addEventListener("seedance_video_progress", (e) => {
      // 把进度转发给 iframe 内的向导
      document.querySelector("iframe")?.contentWindow?.postMessage(
        { type: "seedance_progress", data: e.detail }, "*"
      );
    });

    api.addEventListener("seedance_video_complete", (e) => {
      document.querySelector("iframe")?.contentWindow?.postMessage(
        { type: "seedance_complete", data: e.detail }, "*"
      );
    });

    api.addEventListener("seedance_error", (e) => {
      document.querySelector("iframe")?.contentWindow?.postMessage(
        { type: "seedance_error", data: e.detail }, "*"
      );
    });
  }
});
```

### wizard.html → main.js 的跨 iframe 通信

wizard.html 内的 JS 通过 `window.parent.postMessage` 发送消息给 main.js，
main.js 再通过 `fetch` 调用 `localhost:8188/seedance/*` 路由。

```javascript
// wizard.html 内部触发生成
window.parent.postMessage({
  type: "seedance_generate",
  payload: { session_id, mode, duration, quality, aspect_ratio }
}, "*");

// main.js 接收并转发
window.addEventListener("message", async (e) => {
  if (e.data.type === "seedance_generate") {
    const res = await fetch("/seedance/video/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(e.data.payload)
    });
    const data = await res.json();
    // 把 task_id 传回 iframe
    e.source.postMessage({ type: "seedance_task_created", data }, "*");
  }
});
```

---

## 6. 配置文件约定

API Key 和后端地址存储在 ComfyUI 用户目录下的配置文件：

**路径**：`{ComfyUI_root}/user/default/seedance_config.json`

```json
{
  "api_key": "sk-seed-ab12cdef...",
  "backend_url": "https://api.seedance.cn",
  "language": "zh",
  "last_session_id": "uuid-xxxx"
}
```

Python 节点在启动时读取此文件，`POST /seedance/settings` 时写入。

---

## 7. 错误码约定

| HTTP 状态码 | code 字段 | 含义 |
|------------|-----------|------|
| 401 | `UNAUTHORIZED` | API Key 无效或已撤销 |
| 402 | `INSUFFICIENT_BALANCE` | 余额不足 |
| 429 | `RATE_LIMITED` | 请求过于频繁 |
| 500 | `UPSTREAM_ERROR` | 上游 API（muapi/DeepSeek）异常 |
| 503 | `SERVICE_UNAVAILABLE` | Seedance 生成服务暂时不可用 |

Python 节点在收到 402 时，推送 `seedance_error` WebSocket 事件，向导展示"余额不足"提示并附跳转充值页链接。

---

## 8. 开发环境约定

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SEEDANCE_BACKEND_URL` | Node.js 后端地址 | `http://localhost:3000` |
| `COMFYUI_BASE_URL` | ComfyUI 本地地址（Node.js 后端调用） | `http://localhost:8188` |
| `MUAPI_KEY` | muapi.ai API Key（Node.js 后端环境变量） | — |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | — |
| `DASHSCOPE_API_KEY` | 阿里云 DashScope（Qwen VL）Key | — |
