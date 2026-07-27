# Changelog

## [0.2.0] — 2026-07-27

### Fixed
- generate.json: 完整 8 节点管线 (LoadConditioning→KSampler→VAE→SaveImage)
- Pipeline.encode(): 设置 workflow 变量默认值

### Added
- panel.py: Gradio Web 面板
- adapters/: BackendAdapter 基类 + ComfyUIAdapter

## [0.1.0] — 2026-07-27

### Added
- template.py: WorkflowTemplate (schema驱动) + PlaceholderTemplate (零配置)
- client.py: 通用 ComfyUI HTTP 客户端
- pipeline.py: encode() + generate() 编排
- agent.py: 通用 PromptAgent (YAML 驱动, 无世界观)
- workflows/: encode.json + generate.json
- schemas/: 机器可读变量定义
- config/: prompt_templates.yaml, models.yaml.example, .env.example
- install_custom_nodes.sh: 一键安装 + patch v2.0
- docker-compose.yml + Dockerfile
- README.md: 架构图 + 快速开始 + Troubleshooting
