---
# FILE ENCODING NOTE: This file is UTF-8 without BOM. Windows PowerShell 5.1
# reads it as ANSI; if the Chinese below looks garbled, read with:
#   Get-Content -Encoding UTF8
# VS Code and PowerShell 7 read it correctly.
name: zhipu-vision
description: 用智谱免费视觉模型（glm-4.6v-flash）分析图片并返回文字描述、OCR 提取、内容识别。当当前模型无法直接接收图片（如 DeepSeek 等纯文本模型），且用户提供了本地图片路径或 http(s) 图片 URL、要求描述/分析/识别图片内容或提取图中文字时使用；也用于核验生成或编辑后的图片实际内容。Use when the active model cannot see images and needs vision analysis, description, or OCR via a local path or URL.
---

# 智谱识图（Zhipu Vision）

用智谱免费视觉模型 `glm-4.6v-flash` 分析图片，返回文字描述。适用于当前模型不支持图片输入、或需要从图片提取文字/识别内容的场景。

## 安装

把本文件夹放到 Codex 技能目录（新会话生效）：Windows `C:\Users\<用户名>\.codex\skills\zhipu-vision\`；macOS/Linux `~/.codex/skills/zhipu-vision/`。

## 配置 API Key（必做）

运行一键配置，按提示粘贴 Key（自动写入 `.env` 并验证）：

```powershell
& "scripts\setup.cmd"     # Windows
python3 scripts/setup.py  # macOS / Linux
```

Agent/CI 场景用非交互形式：`python3 scripts/setup.py 你的Key`。手动配置方式见 [usage.md](references/usage.md)。

## 用法

```powershell
& "scripts\analyze_image.cmd" "<图片路径或URL>" ["问题"]    # Windows（启动器自动找 Python）
python3 scripts/analyze_image.py "<图片路径或URL>" ["问题"] # 其他环境
```

常用参数（完整说明见 [usage.md](references/usage.md)）：

- `--pixel-check`：像素级采样作基准；关键细节/识别任务建议加
- `--verify`：两轮独立描述+程序化对比（同一模型自查，不能真正交叉验证）
- `--show-reasoning`：默认不打印思考过程以省 token，需要时加上
- `--no-cache`：跳过缓存

图片支持本地路径、http(s) URL；≤10MB 且最长边 ≤2048px，超出自动压缩/缩放（需 Pillow）。

## 流程

1. 直接传路径/URL；超限图自动压缩/缩放，转换失败才手动处理
2. 输出原样呈现；要中文加 `--language zh`
3. Key 读取顺序：环境变量 → `.env`；报错排查见 [usage.md](references/usage.md)
4. 主模型 `glm-4.6v-flash` 自动回退；429 自动重试
5. 本地图按内容哈希缓存（替换文件不会拿旧结果）；URL 按地址缓存，内容更新需 `--no-cache`
6. 模型输出是"解读"不是事实：细节以像素采样为准；无法由像素证实的具体名称/归属会被列为【推测】
7. 识别类任务不依赖模型下结论：自动像素采样 + 候选假设 + 脚本级"无法确认"结论，需人工/网络核验

## 注意

- `.env` 含真实 Key，已被 .gitignore 忽略，勿提交
- 脚本不保存、不上传图片到第三方（base64 仅发智谱接口）
- 其他 Agent 用 MCP：`scripts/mcp_server.py`（配置见其头部注释与 usage.md）

详细参数、环境变量、故障排查、MCP 配置见 [references/usage.md](references/usage.md)。
