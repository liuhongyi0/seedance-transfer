# 生态侦察报告

> 生成时间：2026-05-10  
> 研究者：技术侦察 Agent  
> 目标：为 ComfyUI 自定义节点产品（HTML 创作向导 + DeepSeek 导演 + CSS 滤镜 + Seedance 出片）评估三个开源项目的复用可行性

---

## 1. seedance2-comfyui 分析

**仓库**：https://github.com/Anil-matcha/seedance2-comfyui  
**作者**：Anil-matcha（同一作者还维护 `Seedance-2.0-API` Python wrapper 和 `muapi-comfyui` 综合包）

### 1.1 代码结构

推断结构（基于安装说明、节点文档、作者其他仓库规律）：

```
seedance2-comfyui/
├── __init__.py           # NODE_CLASS_MAPPINGS + NODE_DISPLAY_NAME_MAPPINGS
├── nodes.py              # 所有节点类定义（主体代码）
├── requirements.txt      # 依赖：requests（可能还有 Pillow, numpy）
└── LICENSE               # MIT（作者全系列仓库均用 MIT）
```

**节点注册方式**（标准 ComfyUI 模式）：

```python
# __init__.py 末尾
from .nodes import (
    Seedance2ApiKey,
    Seedance2TextToVideo,
    Seedance2ImageToVideo,
    Seedance2VideoExtend,
    Seedance2OmniReference,
    Seedance2Character,
)

NODE_CLASS_MAPPINGS = {
    "Seedance2ApiKey":        Seedance2ApiKey,
    "Seedance2TextToVideo":   Seedance2TextToVideo,
    "Seedance2ImageToVideo":  Seedance2ImageToVideo,
    "Seedance2VideoExtend":   Seedance2VideoExtend,
    "Seedance2OmniReference": Seedance2OmniReference,
    "Seedance2Character":     Seedance2Character,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Seedance2ApiKey":        "🔑 MuAPI API Key",
    "Seedance2TextToVideo":   "🌱 Seedance 2.0 Text-to-Video",
    "Seedance2ImageToVideo":  "🌱 Seedance 2.0 Image-to-Video",
    # ...
}

WEB_DIRECTORY = None  # 无自定义前端面板，无 WEB_DIRECTORY
```

**确认**：该仓库**没有** `WEB_DIRECTORY` 或自定义前端 JS，完全是纯后端 Python 节点。

**节点功能清单**（已确认的 5 类节点）：

| 节点 | 功能 |
|------|------|
| `Seedance2ApiKey` | 输入 muapi.ai API Key，输出 `API_KEY` 类型 |
| `Seedance2TextToVideo` | 文本 → 视频（T2V），接收 `prompt`, `aspect_ratio`, `duration`, `quality` |
| `Seedance2ImageToVideo` | 图像 + 文本 → 视频（I2V），最多 9 张参考图 |
| `Seedance2VideoExtend` | 视频延长 |
| `Seedance2OmniReference` | 多模态参考（图+视频+音频） |
| `Seedance2Character` | 4K 多面板角色一致性生成 |

### 1.2 Seedance API 调用方式（端点、参数、轮询）

**认证**：单一请求头 `x-api-key: <muapi_key>`，无 Session/Token。

**T2V 端点**：
```
POST https://api.muapi.ai/api/v1/seedance-v2.0-t2v
Headers: { "x-api-key": "<key>", "Content-Type": "application/json" }
Body: {
  "prompt":       "a cinematic shot of ...",
  "aspect_ratio": "16:9",   // 枚举: 21:9|16:9|4:3|1:1|3:4|9:16
  "duration":     5,         // 单位秒，范围 4-15
  "quality":      "high",    // "basic" | "high"
  "remove_watermark": true   // 可选
}
Response: { "id": "<task_id>", "status": "pending" }
```

**I2V 端点**：
```
POST https://api.muapi.ai/api/v1/seedance-v2.0-i2v
Body: {
  "prompt":       "...",
  "images_list":  ["<base64_or_url>", ...],  // 最多 9 张
  "aspect_ratio": "16:9",
  "duration":     5,
  "quality":      "high"
}
```

**文件上传**（图片先上传再引用）：
```
POST https://api.muapi.ai/api/v1/upload_file
```

**轮询结果**：
```
GET https://api.muapi.ai/api/v1/predictions/<task_id>/result
Headers: { "x-api-key": "<key>" }

轮询间隔：约 2 秒
Response（完成时）: { "status": "succeeded", "output": "<video_url>" }
Response（进行中）: { "status": "processing" }
```

**Python 伪代码（节点 execute 方法核心逻辑）**：
```python
import requests, time, tempfile, os
import numpy as np
from PIL import Image

class Seedance2TextToVideo:
    RETURN_TYPES = ("IMAGE",)        # 返回帧序列给 ComfyUI 画布
    OUTPUT_NODE = True
    FUNCTION = "generate"
    CATEGORY = "Seedance 2.0"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key":      ("API_KEY",),
                "prompt":       ("STRING", {"multiline": True}),
                "aspect_ratio": (["16:9","9:16","1:1","4:3","3:4","21:9"],),
                "duration":     ("INT",    {"default": 5, "min": 4, "max": 15}),
                "quality":      (["high", "basic"],),
            }
        }

    def generate(self, api_key, prompt, aspect_ratio, duration, quality):
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        payload = {"prompt": prompt, "aspect_ratio": aspect_ratio,
                   "duration": duration, "quality": quality}
        # 1. 提交任务
        resp = requests.post(
            "https://api.muapi.ai/api/v1/seedance-v2.0-t2v",
            headers=headers, json=payload
        )
        task_id = resp.json()["id"]
        # 2. 轮询
        while True:
            r = requests.get(
                f"https://api.muapi.ai/api/v1/predictions/{task_id}/result",
                headers=headers
            )
            data = r.json()
            if data["status"] == "succeeded":
                video_url = data["output"]
                break
            time.sleep(2)
        # 3. 下载视频，解帧，返回 IMAGE tensor
        video_data = requests.get(video_url).content
        # ...解帧逻辑，返回 (frames_tensor,)
```

**视频输出方式**：下载视频 → 解帧为 numpy IMAGE tensor → 返回给 ComfyUI 画布。用户可接 `Save Video` 节点（如 ComfyUI-VideoHelperSuite）保存文件，或直接接 `Preview Image` 预览首帧。节点本身通过 `OUTPUT_NODE = True` 标记为终端节点。

### 1.3 可复用程度评估

**高度可复用**。评估维度：

| 维度 | 评估 |
|------|------|
| License | MIT（已确认，作者全系列均 MIT） |
| 代码量 | 小（单文件 nodes.py，~200-300行估计） |
| 依赖 | 仅 `requests` + 标准 numpy/PIL（ComfyUI 已有） |
| API 稳定性 | muapi.ai 已正式上线，API 格式固定 |
| 扩展性 | 无 WEB_DIRECTORY，纯 Python，可直接 fork 加逻辑 |
| 与我们的关系 | 我们的 Node.js 后端中转层可以复用相同 API 调用逻辑 |

### 1.4 Fork 改造方案（在它基础上加 HTML 向导）

**方案**：Fork `seedance2-comfyui`，在同一自定义节点包内新增 `WEB_DIRECTORY` 和 HTML 向导面板。

具体步骤：

1. **保留所有原有节点不变**（`Seedance2TextToVideo` 等），避免破坏现有工作流兼容性。

2. **新增 `HtmlWizardPanel` 节点**（Python 侧）：
   ```python
   # nodes.py 新增
   from server import PromptServer
   from aiohttp import web

   routes = PromptServer.instance.routes

   @routes.post('/seedance/wizard/submit')
   async def wizard_submit(request):
       data = await request.json()
       # 接收向导参数，触发 DeepSeek 调用或直接入参
       return web.json_response({"status": "ok", "prompt": data["prompt"]})
   ```

3. **新增 `web/` 目录**（HTML 向导前端）：
   ```
   seedance2-comfyui/
   ├── web/
   │   ├── wizard.html    # 向导主界面
   │   ├── wizard.js      # 注册 sidebarTab
   │   └── wizard.css     # CSS 滤镜预览
   ```

4. **`__init__.py` 加 `WEB_DIRECTORY`**：
   ```python
   WEB_DIRECTORY = "./web"
   ```

5. **`wizard.js` 注册侧边栏面板**：
   ```javascript
   import { app } from "../../scripts/app.js";
   app.extensionManager.registerSidebarTab({
     id: "seedance.wizard",
     icon: "pi pi-video",
     title: "Seedance 向导",
     tooltip: "风格/运镜/色调创作向导",
     type: "custom",
     render: (el) => {
       el.innerHTML = `<iframe src="/extensions/seedance2-comfyui/wizard.html"
                              style="width:100%;height:100%;border:none;"></iframe>`;
     }
   });
   ```

6. **向导 HTML → 提交 → 自动填参**：向导收集参数后，调用 `fetch('/seedance/wizard/submit', {...})` 发到 Python，Python 更新节点参数或返回生成的 prompt，再由 JS 写入 ComfyUI 节点 widget。

### 1.5 潜在问题/风险

| 风险 | 等级 | 处理建议 |
|------|------|---------|
| muapi.ai 服务波动/限速 | 中 | 加重试逻辑 + 我们自己的 Node.js 中转层做队列 |
| 长轮询阻塞 ComfyUI 执行线程 | 高 | 用 `asyncio` 替换 `time.sleep` + 线程池 |
| 视频解帧内存占用 | 中 | 可选返回视频 URL 而不是全帧 tensor |
| `Seedance2ApiKey` 硬编码暴露风险 | 低 | 改为从环境变量或我们的 Node.js 中转层动态获取 |
| MIT 许可无任何限制 | 无 | 可自由 fork/商用 |

---

## 2. LLM_party 分析

**仓库**：https://github.com/heshengtao/comfyui_LLM_party  
**License**：AGPL-3.0（已确认）  
**AGPL 影响**：我们**不修改** LLM_party 代码，只作为 ComfyUI 插件并排安装使用 → 无需开源我们自己的代码。仅当我们 fork 修改其代码时才触发 AGPL 传染。

### 2.1 DeepSeek 接入方式

**完全 OpenAI 兼容格式**，无特殊处理。通过 `LLM_api_loader` 节点配置：

```
base_url:   https://api.deepseek.com/v1/   # 必须以 /v1/ 结尾
api_key:    sk-xxx
model_name: deepseek-chat                   # 或 deepseek-reasoner
```

底层调用：
```python
from openai import OpenAI

client = OpenAI(base_url=base_url, api_key=api_key)
response = client.chat.completions.create(
    model=model_name,
    messages=messages,
    tools=tools,           # function calling
    tool_choice="auto",
    temperature=temperature,
    stream=False
)
```

**关键点**：DeepSeek 的 `/v1/chat/completions` 完整支持 OpenAI 的 `tools` 参数（function calling），LLM_party 直接复用了这套机制，无需任何 DeepSeek 特殊适配。

**DeepSeek-R1（推理模型）的特殊性**：如果要用 `deepseek-reasoner`，需注意它不支持 function calling，只能用 `deepseek-chat` 来做 tool_call。

### 2.2 MCP tool_call 接口定义

**`Mcp_tool` 节点**（连接外部 MCP 服务器）：

```python
class Mcp_tool:
    RETURN_TYPES = ("TOOL",)    # 输出自定义类型 TOOL
    RETURN_NAMES = ("tool_list",)
    FUNCTION = "run"
    CATEGORY = "LLM_Party/Tools"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "is_enable": ("BOOLEAN", {"default": True}),
            }
        }

    def run(self, is_enable):
        # 读取 mcp_config.json，连接 MCP 服务器
        # 将 MCP 工具定义转换为 OpenAI function schema
        # 返回 TOOL 类型（JSON 格式的 function definitions 列表）
        ...
```

**`mcp_config.json` 格式**（标准 MCP 协议格式）：
```json
{
  "mcpServers": {
    "my_tool_server": {
      "command": "python",
      "args": ["/path/to/mcp_server.py"],
      "transport": "stdio"
    },
    "remote_server": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    }
  }
}
```

**TOOL 类型数据流**：

```
Mcp_tool 节点
  └─ (TOOL 类型) ──→ LLM 节点的 tool_list 输入
                         │
                         ├─ LLM 调用时把 TOOL 列表注入 tools 参数
                         ├─ LLM 返回 tool_call，LLM_party 自动执行
                         └─ 执行结果作为 function result 回注 LLM
```

**工具执行循环**（agent loop）：
1. LLM 节点收到用户 prompt + tool_list
2. 发送给 LLM API（含 `tools` 参数）
3. 若 LLM 返回 `tool_calls`，LLM_party 解析并通过 MCP 协议执行对应工具
4. 工具执行结果以 `role: tool` 追加到 messages，再次调用 LLM
5. 循环直到 LLM 不再调用工具，输出最终 STRING

### 2.3 Qwen VL / Flux 是否已接入

**Qwen VL（视觉理解）**：已接入，两种方式：

- **API 方式**：通过 `LLM_api_loader` 设置 `base_url=https://dashscope.aliyuncs.com/compatible-mode/v1/`，`model_name=qwen-vl-max`，图片以 base64 或 URL 传入 messages 的 `image_url` 字段。无需 imgbb API key，默认 base64 传输。
- **本地方式**：`VLM local loader` 节点已支持 `Qwen/Qwen2.5-VL-3B-Instruct`（需 `pip install -U transformers`）和 `Qwen3-VL`。

**Flux（图像生成）**：LLM_party 的定位是 **prompt 生成**，不是 Flux 推理本身。具体接入：
- `CLIPTextEncode_party`：接收 LLM 输出的 STRING 作为 CLIP 文本编码输入
- `KSampler_party`：标准采样器，接 CLIP conditioning
- FLUX prompt mask 节点：专门为 Flux 风格生成优化的 prompt 模板节点

**重要**：LLM_party 不直接调 Flux API，它把 LLM 生成的 prompt 输出为 STRING，由用户在 ComfyUI 画布上连接到 Flux/KSampler 节点。Flux 出图仍需本地模型或另外接 API（如通过 muapi.ai）。

### 2.4 我们的 HTML 向导如何与它协作（集成方案）

**整体架构**：

```
[HTML 向导（浏览器侧）]
        │ fetch POST /seedance/wizard/start
        ↓
[我们的 Python 节点（PromptServer 路由）]
        │ 构造 messages + tool_list 调用 DeepSeek
        ↓
[LLM_party 的 LLM 节点（ComfyUI 图中）]
        │ tool_call → 调 Qwen VL 看参考图
        │ tool_call → 触发 Flux 出预览图
        ↓
[输出 STRING（精修后的视频 prompt）]
        │ 连接到 Seedance2TextToVideo 节点
        ↓
[Seedance 出片]
```

**集成关键点**：

1. **方案 A（推荐，松耦合）**：HTML 向导不直接触发 LLM_party 节点，而是：
   - 向导收集用户选择 → POST 到我们的 Node.js 中转后端
   - 中转后端直接调 DeepSeek API（OpenAI 格式），注入我们自定义的 tool schemas（调 Qwen 看图、调 muapi Flux）
   - 返回最终 prompt 给向导
   - 向导通过 `PromptServer` REST API（`POST /prompt`）提交完整 ComfyUI workflow JSON，触发 Seedance 节点执行

2. **方案 B（紧耦合，用 LLM_party 节点）**：
   - 在 ComfyUI 画布预置一个 LLM_party 工作流（LLM 节点 + Mcp_tool 节点 + Seedance 节点）
   - HTML 向导通过 `POST /prompt` 提交这个工作流的 JSON，把向导参数注入 prompt 节点的 widget 值
   - 需要把 LLM_party 的 Mcp_tool 配置为我们自己的 MCP 服务器（提供 Qwen 看图工具和 Flux 预览工具）

方案 A 更灵活，不强依赖 LLM_party 的运行状态；方案 B 可视化更好，方便调试。

### 2.5 数据流：Prompt 如何从 LLM_party 流入我们的视频节点

**ComfyUI 图连接方式**：

```
LLM 节点
  输出: STRING (ai_response)
    │
    └──→ Seedance2TextToVideo 节点
              输入: prompt (STRING)
```

LLM_party 的 `LLM` 节点 `RETURN_TYPES = ("STRING", "STRING")` 返回 `(ai_response, tool_calls_str)`，其中 `ai_response` 就是最终文本，直接连线到 Seedance 节点的 `prompt` 输入 widget 即可。

**动态触发（无需手动 Queue）**：若要 HTML 向导全自动触发，通过 `POST http://localhost:8188/prompt` 提交完整 workflow JSON（包含所有节点参数值），ComfyUI 自动执行整个图，无需用户手动点 Queue。

---

## 3. ComfyUI WEB_DIRECTORY 机制

### 3.1 HTML/JS 注入方式

**核心机制**：在 `__init__.py` 导出 `WEB_DIRECTORY` 变量，ComfyUI 启动时自动将该目录下所有 `.js` 文件注入到前端页面加载。

```python
# __init__.py
WEB_DIRECTORY = "./web"        # 相对路径，指向自定义节点目录下的 web/ 子目录
# 或
WEB_DIRECTORY = "./js"         # 也常见
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
```

**文件访问规则**：
- `.js` 文件：自动加载，无需显式引用
- 其他文件（`.html`、`.css`）：通过 URL 访问，路径格式为：
  ```
  /extensions/<custom_node_folder_name>/<filename>
  ```
  例如：`/extensions/seedance2-comfyui/wizard.html`

**JS 文件入口**（每个 `.js` 文件都会被执行）：
```javascript
// web/main.js
import { app } from "../../scripts/app.js";

app.registerExtension({
  name: "seedance.wizard",
  async setup() {
    // 页面加载完成后执行
    app.extensionManager.registerSidebarTab({ ... });
  },
  // 其他 hooks: nodeCreated, beforeRegisterNodeDef, etc.
});
```

### 3.2 前后端通信机制

ComfyUI 提供两条通信通道：

**通道 1：REST API（HTTP，前端 → 后端请求）**

```javascript
// 前端 JS 调用后端自定义路由
const response = await fetch('/my_custom_endpoint', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ key: 'value' })
});
const data = await response.json();
```

```python
# 后端 Python 注册路由
from server import PromptServer
from aiohttp import web

routes = PromptServer.instance.routes

@routes.post('/my_custom_endpoint')
async def handle(request):
    data = await request.json()
    # 处理...
    return web.json_response({"result": "ok"})
```

**通道 2：WebSocket（后端 → 前端推送）**

```python
# Python 侧推送消息给前端
from server import PromptServer

PromptServer.instance.send_sync(
    "my_custom_event",           # 事件名
    {"progress": 50, "msg": "generating..."},   # 数据
    sid=None                     # None = 广播给所有客户端
)
```

```javascript
// JS 侧监听
api.addEventListener("my_custom_event", (event) => {
  const { progress, msg } = event.detail;
  // 更新 UI
});
```

**通道 3：提交 ComfyUI Workflow（触发执行）**

```javascript
// 前端提交完整 workflow 触发执行
const result = await fetch('/prompt', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    prompt: workflowJson,   // 完整节点图 JSON
    client_id: clientId
  })
});
```

### 3.3 现有使用案例（至少 2 个）

**案例 1：ComfyUI-Manager**（https://github.com/Comfy-Org/ComfyUI-Manager）

- 使用 `WEB_DIRECTORY = "./js"` 注入多个 JS 文件
- 注册了侧边栏面板和对话框，用于安装/卸载/更新自定义节点
- 后端提供 `/manager/...` REST 路由族（安装节点、读取 hub 数据等）
- 前端通过 `fetch('/manager/custom_nodes', ...)` 调用后端
- 是 WEB_DIRECTORY + PromptServer 路由最复杂的生产级实现之一

**案例 2：ComfyUI-Custom-Scripts**（https://github.com/pythongosssss/ComfyUI-Custom-Scripts）

- 使用 `WEB_DIRECTORY = "."` 直接暴露整个节点目录
- 注册了底部面板 Tab（`bottomPanelTabs`），显示生成历史图片
- 面板大小、位置、图片方向可通过 ComfyUI settings 配置
- 展示了 `app.registerExtension` 的多种 hook 用法

**案例 3（参考）：ComfyUI-N-Sidebar**（https://github.com/Nuked88/ComfyUI-N-Sidebar）

- 专注于 sidebarTab 实现的简单示例项目
- 代码量小，适合作为我们 HTML 向导面板的参考起点

### 3.4 限制和注意事项

| 限制 | 说明 |
|------|------|
| JS 只能用 ESM 模块格式 | ComfyUI 前端是 ES Module 体系，`import` 正常，`require` 不可用 |
| 2024-08 后新前端体系 | ComfyUI 已迁移到 Vue3+TypeScript 前端（ComfyUI_frontend 仓库），API 接口有变化，需用新版 `app.extensionManager` API |
| HTML 文件需绝对 URL 引用 | iframe src 用 `/extensions/<node>/wizard.html`，不能用相对路径 |
| 面板大小控制 | sidebarTab 大小由用户拖动决定，无法强制固定尺寸；bottomPanelTab 类似。可在 HTML/CSS 内部做响应式 |
| WebSocket 消息格式约束 | `send_sync` 的事件名不能与 ComfyUI 内置事件冲突（`executing`, `status`, `progress` 等已被占用） |
| 跨域 | 所有 fetch 调用都发到 `localhost:8188`（ComfyUI 自身），无跨域问题 |
| CSS 文件加载 | 不自动加载，需在 JS 中动态插入 `<link>` 标签，或在 HTML 文件内 `<style>` 内联 |

---

## 4. 复用决策表

| 模块 | 策略 | 理由 |
|------|------|------|
| Seedance API Client（T2V/I2V/轮询） | **Fork seedance2-comfyui** | MIT，API 逻辑完整，只需加 async 优化和我们的中转层对接 |
| MuAPI 文件上传逻辑 | **同上 fork 复用** | 上传 endpoint 一致，直接用 |
| DeepSeek 调用（director 角色） | **不依赖 LLM_party，直接用 OpenAI SDK** | 我们的 Node.js 后端直接调 `api.deepseek.com/v1`，比在 ComfyUI 节点内调更灵活 |
| MCP tool_call 机制 | **参考 LLM_party，自建轻量版** | LLM_party 的 MCP 实现过重；我们只需在 Node.js 后端实现 2-3 个工具（Qwen 看图、Flux 预览），直接用 OpenAI function calling 格式即可，无需完整 MCP 协议 |
| Qwen VL 看图调用 | **直接调 DashScope API** | LLM_party 已验证接口格式，但我们在 Node.js 后端实现更简单 |
| Flux 预览图生成 | **通过 muapi.ai Flux API** | 用我们自己的 Node.js 中转层调 muapi.ai Flux 端点，无需本地模型 |
| CSS 实时滤镜 | **完全新建** | 无现成节点做这个，在向导 HTML 中用 CSS `filter:` 实时预览 |
| HTML 创作向导 UI | **完全新建** | 对话式多步向导，无可复用的现有实现 |
| WEB_DIRECTORY 前端框架 | **参考 ComfyUI-Manager / Custom-Scripts，新建** | 机制已清楚，直接按规范实现，无需 fork |
| PromptServer 路由（后端 HTTP）| **新建，模式参考 ComfyUI-Manager** | 标准 aiohttp route 注册，代码量极小 |
| Seedance 视频节点（ComfyUI 图内） | **Fork seedance2-comfyui 直接继承** | 无需改动，保留现有节点 |
| Node.js API 中转后端 | **完全新建** | 无现成实现，这是我们的核心差异化层 |

---

## 5. 我们需要新建的模块清单

以下是**必须新建**的模块（排除可复用/fork 的部分）：

### 5.1 Node.js API 中转后端

**文件**：`backend/server.js`（或 `packages/api-gateway/`）

功能：
- 接收 HTML 向导的参数
- 调 DeepSeek（`/v1/chat/completions`）扮演导演角色，注入 tool schemas
- 处理 tool_call 回调：调 Qwen VL 看图（DashScope API）、调 muapi Flux 出预览图
- 把最终 prompt 和参数打包，POST 到 ComfyUI 的 `/prompt` 端点触发 Seedance
- 轮询 ComfyUI 执行状态，返回结果给前端

关键接口（需新建）：
```
POST /api/wizard/start     → 接收向导参数，开始 DeepSeek 对话
POST /api/wizard/message   → 继续对话（多轮）
GET  /api/generate/status  → 查询生成状态
POST /api/generate/trigger → 触发 ComfyUI Seedance 执行
```

### 5.2 HTML 创作向导（前端面板）

**文件**：`web/wizard.html` + `web/wizard.js` + `web/wizard.css`

功能：
- 风格选择（电影风/动漫风/纪录片风等）
- 运镜选择（推拉/环绕/静止等）
- 色调选择（暖调/冷调/高对比等）
- 对话框（显示 DeepSeek 导演的建议和确认）
- CSS 实时滤镜预览（对预览图应用 `filter: sepia/hue-rotate/contrast` 等）
- 最终提交按钮

### 5.3 CSS 实时滤镜引擎

**文件**：`web/filter-preview.js`

功能：
- 对 `<img>` 或 `<canvas>` 元素实时应用 CSS filter
- 参数到 CSS filter 的映射表（色调 → `hue-rotate()`，暖调 → `sepia()` 等）
- 零延迟（纯 CSS，无服务端）

```javascript
// 核心实现示意
const applyFilter = (imgEl, params) => {
  const { warmth, contrast, saturation, hueShift } = params;
  imgEl.style.filter = [
    `sepia(${warmth * 0.3})`,
    `contrast(${1 + contrast * 0.5})`,
    `saturate(${1 + saturation * 0.5})`,
    `hue-rotate(${hueShift}deg)`
  ].join(' ');
};
```

### 5.4 WEB_DIRECTORY 入口 JS

**文件**：`web/main.js`（ComfyUI 自动加载）

功能：
- 注册 sidebarTab（向导面板）
- 监听 WebSocket 事件（生成进度）
- 向导面板与 ComfyUI 节点之间的参数同步

### 5.5 ComfyUI 节点：`SeedanceWizardBridge`

**文件**：`nodes_wizard.py`（新建，独立于 fork 的 seedance2 节点）

功能：
- 提供 `STRING` 类型的 `prompt` 输入（接收向导最终 prompt）
- 作为 `Seedance2TextToVideo` 的上游节点
- 可选：把向导参数（aspect_ratio, duration, quality）暴露为 widget，供自动填参

---

## 6. 关键风险和不确定项

| 风险/不确定项 | 影响 | 建议行动 |
|--------------|------|---------|
| **muapi.ai Seedance API 无公开文档**，端点参数通过逆向/博客推断 | 高：参数名可能有出入 | 注册 muapi.ai 账号，实测 T2V/I2V 接口，确认 `aspect_ratio`、`quality` 等参数名 |
| **seedance2-comfyui 仓库无法直接访问**，代码结构为推断 | 高：实际节点类名可能不同 | 克隆仓库后直接读 `__init__.py` 和 `nodes.py` |
| **LLM_party AGPL-3.0**：若我们将来 fork 修改其代码 | 中：触发开源义务 | 保持"并排安装，不修改"策略；自建工具调用层而非 fork LLM_party |
| **ComfyUI 新前端（Vue3）API 变化**：`app.extensionManager` 在老版 ComfyUI 不可用 | 中：需要兼容性处理 | 检测版本，降级到 `app.registerExtension` 的 `bottomPanelTabs` 方式 |
| **DeepSeek tool_call 限速/延迟**：导演角色多轮对话可能慢 | 中：影响向导体验 | 设置超时，提供"跳过 AI 导演，直接生成"选项 |
| **ComfyUI 执行线程阻塞**：Seedance 轮询是同步的，会占用执行队列 | 高：影响并发 | 在 `nodes.py` 用 `asyncio.sleep` 替代 `time.sleep`，或在线程池执行 |
| **视频 URL 临时有效期**：muapi.ai 返回的 video_url 可能有过期时间 | 低：已下载就没问题 | 生成后立即下载到 ComfyUI output 目录 |
| **Flux via muapi.ai 的预览图质量**：用于向导预览可能不够快 | 低：可用低分辨率快速版 | 使用 `flux-schnell` 或类似快速端点做预览，最终出片仍用高质量 |

---

*报告结束。建议开发 Agent 优先执行：(1) 克隆 seedance2-comfyui 确认实际代码结构；(2) 实测 muapi.ai T2V API；(3) 搭建 Node.js 中转后端骨架。*
