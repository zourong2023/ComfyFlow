# ComfyFlow

**ComfyUI Conditioning Cache Pipeline + Web Panel — One-click deploy, zero CLIP reload.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What is ComfyFlow?

ComfyFlow splits ComfyUI image generation into **two independent workflows**:

1. **Encode Workflow** — Loads CLIP once, encodes your prompt into a `.bin` conditioning file, then unloads CLIP.
2. **Generate Workflow** — Loads the `.bin` file directly (no CLIP), runs UNET + VAE + LoRA chain, and outputs images.

**Result**: Same prompt? Encode once, generate N times. CLIP model loads only on first run. Every subsequent generation skips the heaviest model entirely.

---

## Quick Start (Docker)

```bash
docker-compose up -d
# Open http://localhost:8500 in browser
```

## Quick Start (Manual)

```bash
# 1. Install
pip install comfyflow

# 2. Configure (edit config/models.yaml with your model paths)
cp .env.example .env

# 3. Launch web panel
comfyflow panel --comfyui-url http://localhost:8188
```

## Prerequisites

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) running with API enabled (Python 3.11+, CUDA GPU)
- [SaveAndLoadPromptCondition](https://github.com/endman100/ComfyUI-SaveAndLoadPromptCondition) custom node **v2.0** (see Custom Node Setup below)
- Python 3.11+ for the ComfyFlow client (can run on a different machine than ComfyUI)

---

## Architecture

```
[User Browser] → [Gradio Panel :8500] → [comfyflow.Client] → [ComfyUI :8188]
                                                   ↓
                                           [conditionings/ cache]
```

### Dual Workflow Pipeline

```
┌─ Cold Start (prompt changed) ─────────────────────────┐
│  POST encode_workflow.json                            │
│  ├── CLIPLoader → CLIPTextEncode(+) → SaveConditioning│
│  └── CLIPLoader → CLIPTextEncode(-) → SaveConditioning│
│  Result: {prefix}_pos_{timestamp}_conditionings.bin   │
│         {prefix}_neg_{timestamp}_conditionings.bin    │
└───────────────────────────────────────────────────────┘
                         ↓
┌─ Hot Path (every generation) ─────────────────────────┐
│  POST generate_workflow.json                          │
│  ├── LoadContditioning(+) → KSampler(+)               │
│  ├── LoadContditioning(-) → KSampler(-)               │
│  ├── UNETLoader → LoRA Chain → ModelSamplingAuraFlow  │
│  ├── EmptySD3LatentImage → KSampler(latent)           │
│  └── VAELoader → VAEDecode → SaveImage                │
│  (NO CLIP nodes — conditioning loaded from disk)      │
└───────────────────────────────────────────────────────┘
```

---

## Features

- **Zero CLIP Reload**: Encode once, generate unlimited times
- **Web Panel (Gradio)**: Text input → image output, no code
- **Turbo Mode Toggle**: 4-step Lightning LoRA or 50-step full quality
- **Multi-Backend**: ComfyUI / ModelScope / Custom HTTP API
- **Config-Driven**: All models, LoRAs, paths defined in `models.yaml`
- **Docker Ready**: `docker-compose up` and you're running

---

## Configuration

### models.yaml

```yaml
comfyui:
  url: "http://localhost:8188"

models:
  clip:
    name: "your-clip-model.safetensors"
    type: "qwen_image"
  unet:
    name: "your-unet-model.safetensors"
  vae:
    name: "your-vae-model.safetensors"
  loras:
    - name: "lightning-lora.safetensors"
      strength: 1.0
    - name: "style-lora.safetensors"
      strength: 0.6

turbo_mode:
  enabled: true
  steps: 4
  cfg: 1
```

### prompt_templates.yaml

```yaml
# Qwen-Image (Chinese natural language)
qwen:
  positive: |
    高质量动漫插图，{user_prompt}，sharp clean lineart，cel shading
  negative: |
    低分辨率，低画质，肢体畸形，手指畸形，画面过饱和

# SDXL (English comma tags)
sdxl:
  positive: |
    masterpiece, best quality, ultra detailed, {user_prompt}, cinematic lighting
  negative: |
    lowres, bad anatomy, deformed, extra fingers, watermark

# Your custom model
custom:
  positive: |
    {user_prompt}
  negative: |
    low quality
```

### .env.example

```bash
# ComfyUI server
COMFYUI_URL=http://localhost:8188
COMFYUI_AUTH_USER=
COMFYUI_AUTH_PASS=

# Web panel
HOST=0.0.0.0
PORT=8500
```

---

## Web Panel

```bash
comfyflow panel
```

Opens a Gradio interface at `http://localhost:8500` with:

| Control | Description |
|---------|-------------|
| Prompt Input | Your text prompt |
| Negative Prompt | Quality control |
| Model Selector | Choose from models.yaml |
| Turbo Toggle | 4-step fast or 50-step quality |
| Generate Button | One click to image |
| Gallery | Browse generation history |
| Status Bar | ComfyUI connection + cache state |

---

## Python API

```python
from comfyflow import Client, WorkflowTemplate

client = Client("http://localhost:8188")

# Encode conditioning (runs once per unique prompt)
pos_file, neg_file = client.encode(
    positive_prompt="masterpiece, 1girl, looking at viewer",
    negative_prompt="lowres, bad anatomy",
    prefix="my_character"
)

# Generate images (no CLIP reload)
result = client.generate(
    pos_cond_file=pos_file,
    neg_cond_file=neg_file,
    seed=42,
    turbo_mode=True
)
```

---

## Project Structure

```
ComfyFlow/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   ├── models.yaml              # Model configuration template
│   ├── prompt_templates.yaml    # Generic prompt templates
│   └── workflow_schema.json     # Variable definitions for workflows
├── workflows/                   # ComfyUI JSON templates
│   ├── encode_workflow.json
│   └── generate_workflow.json
├── src/
│   └── comfyflow/
│       ├── __init__.py
│       ├── client.py            # HTTP API client
│       ├── workflow.py          # WorkflowTemplate class
│       ├── pipeline.py          # Encode + Generate orchestration
│       ├── panel.py             # Gradio web panel
│       └── adapters/            # Multi-backend adapters
│           ├── comfyui.py
│           └── modelscope.py
├── tests/
│   └── test_client.py
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── api.md
└── scripts/
    ├── setup.sh
    └── install_custom_nodes.sh  # Auto git clone required ComfyUI nodes
```

---

## Custom Node Setup

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/endman100/ComfyUI-SaveAndLoadPromptCondition.git
```

**⚠️ 关键步骤：原版 `nodes.py` 没有 `filename` 参数，必须替换为 v2.0：**

```bash
# 下载 patched nodes.py（添加了 filename 输入，移除硬编码时间戳）
curl -o ComfyUI-SaveAndLoadPromptCondition/nodes.py \
  https://raw.githubusercontent.com/your-org/ComfyFlow/main/scripts/install_custom_nodes.sh
# 或用项目自带的 patch 脚本：
bash scripts/install_custom_nodes.sh /path/to/ComfyUI
```

**验证：** 重启 ComfyUI 后运行以下命令，确认 `SaveConditioning` 节点暴露 `filename` 输入：

```bash
curl http://localhost:8188/object_info/SaveConditioning | grep filename
```

预期输出应包含 `"filename"` 字段。如果没有，说明 `nodes.py` 未正确更新。

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

1. Fork the repo
2. Create a feature branch
3. Make changes, add tests
4. Submit PR

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Related Projects

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — The underlying generation engine
- [SaveAndLoadPromptCondition](https://github.com/endman100/ComfyUI-SaveAndLoadPromptCondition) — Conditioning persistence node

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| **`LoadContditioning` dropdown empty** | No conditioning files generated yet, or browser cache | Run encode first, then refresh ComfyUI web UI |
| **`401 Unauthorized`** | ComfyUI behind auth but no credentials in config | Set `COMFYUI_AUTH_USER` / `COMFYUI_AUTH_PASS` in `.env` |
| **Black images after SetNode/GetNode** | KJNodes memory corruption | Remove SetNode/GetNode from workflow, restart ComfyUI process |
| **`stat: path should be string, bytes... NoneType`** | Conditioning file not found | Check `models/conditionings/` exists and has `.bin` files. Verify `nodes.py` is v2.0 |
| **ComfyUI manager crashes on startup** | `raw.githubusercontent.com` unreachable | `export COMFYUI_MANAGER_SKIP_UPDATE=true` before starting |

---

## FAQ

**Q: Does this work with any ComfyUI workflow?**
A: The encode/generate split works with any workflow that uses CLIPTextEncode. You provide your own workflow JSON templates in `workflows/`.

**Q: What models are supported?**
A: Any model supported by ComfyUI. The default workflows target Qwen-Image 2512, but you can swap in SDXL, SD3, Flux, etc.

**Q: Do I need to keep ComfyUI running?**
A: Yes. ComfyFlow is a client/panel layer on top of ComfyUI's API. ComfyUI must be running separately.

**Q: Can I use this without the Web Panel?**
A: Yes. `from comfyflow import Client` works as a pure Python library.
