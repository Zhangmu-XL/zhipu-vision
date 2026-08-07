# Zhipu Vision（智谱识图）

用智谱**免费**视觉模型 `glm-4.6v-flash` 分析图片，让"看不了图"的 Agent（如 DeepSeek 等纯文本模型）也能描述图片内容、提取图中文字、识别实体。支持本地图片路径与 http(s) URL，可作为 Codex Skill 或 MCP 服务器使用。

## 特性

- 免费模型：`glm-4.6v-flash`（128K 上下文），不可用时自动回退 `glm-4v-flash` / `glm-4.1v-thinking-flash`
- 自动预处理：本地图片 ≤10MB 且最长边 ≤2048px，超出自动压缩/缩放；相机 RAW（ARW/CR2/NEF/DNG 等）自动扫描文件内 JPEG 段并取最大者
- 像素级基准：`--pixel-check` 输出分区颜色网格 + 主色统计，作为独立于视觉模型的"事实基准"，把无法由像素证实的具体名称/归属分离为【推测】
- 两轮核对：`--verify` 二次独立描述 + 特征词表程序化对比，检出确认性表述会标记降级
- 本地缓存：默认 30 天，本地图片按内容哈希（替换文件自动失效），`--no-cache` 跳过
- 零依赖核心：`analyze_image.py` 仅用 Python 标准库；Pillow 为可选项（影响自动缩放与像素采样）
- 多端复用：CLI 直接跑，或经 `mcp_server.py` 接入 Claude Desktop / Cursor / Cline 等
- 一键配置：`scripts/setup.py` 交互式粘贴 Key，自动验证并写入 `.env`

## 目录结构

```
zhipu-vision/
├── SKILL.md                 # Codex Skill 触发说明与流程
├── .env.example             # API Key 配置模板（复制为 .env 使用）
├── .gitignore
├── requirements-mcp.txt     # MCP 服务器依赖
├── agents/openai.yaml       # Skill UI 元数据
├── references/usage.md      # 参数/环境变量/故障排查详情
└── scripts/
    ├── analyze_image.py     # 核心脚本（零依赖）
    ├── analyze_image.cmd    # Windows 启动器（自动探测 Python）
    ├── mcp_server.py        # MCP 服务器（供其他 Agent）
    ├── setup.py             # 一键配置 API Key
    └── setup.cmd            # Windows 一键配置启动器
```

## 安装（作为 Codex Skill）

把 `zhipu-vision/` 文件夹放到 Codex 技能目录，然后**完全重启 Codex 并新开会话**：

- Windows：`C:\Users\<用户名>\.codex\skills\zhipu-vision\`
- macOS / Linux：`~/.codex/skills/zhipu-vision/`（或 `$CODEX_HOME/skills/zhipu-vision/`）

## 配置 API Key

Key 到 [open.bigmodel.cn](https://open.bigmodel.cn) 免费申请。三选一：

1. 一键配置（推荐）：进入 `zhipu-vision` 目录后运行

   ```powershell
   & "scripts\setup.cmd"     # Windows
   python3 scripts/setup.py  # macOS / Linux
   ```

   按提示粘贴 Key，脚本自动验证并写入 `.env`。非交互环境用 `python3 scripts/setup.py 你的Key`。

2. 环境变量：`export ZHIPU_API_KEY=你的Key`（Windows: `$env:ZHIPU_API_KEY = "你的Key"`）

3. 手动：复制 `.env.example` 为 `.env` 并填入 Key。

读取顺序：环境变量 `ZHIPU_API_KEY` → 技能目录 `.env`。

## 使用

```powershell
# Windows（启动器自动找 Python，绕开商店占位符）
& "scripts\analyze_image.cmd" "D:\photo.jpg" "提取图中所有文字"

# macOS / Linux
python3 scripts/analyze_image.py "https://example.com/a.png" "描述这张图"
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `image` | 本地路径或 http(s) URL；超出 10MB/2048px 自动压缩缩放；RAW 自动提取内嵌 JPEG |
| `question` | 针对图片的问题/指令 |
| `--detail brief\|standard\|detailed` | 详细程度；含"提取/所有/详细/完整"等关键词时自动升级为 detailed |
| `--language auto\|zh\|en` | 回答语言 |
| `--thinking` | 开启深度思考 |
| `--show-reasoning` | 打印思考过程（默认不打印以省 token） |
| `--pixel-check` | 像素级基准（分区颜色网格+主色统计），注入提示词锚定事实 |
| `--verify` | 两轮独立描述 + 程序化对比 |
| `--save-preview PATH` | 把 RAW 提取出的 JPEG 预览落盘 |
| `--no-cache` | 跳过本地缓存 |
| `--cache-age DAYS` | 缓存有效期，默认 30 天 |

完整示例见 [references/usage.md](zhipu-vision/references/usage.md)。

## 接入其他 Agent（MCP）

```bash
pip install -r requirements-mcp.txt
python scripts/mcp_server.py   # stdio 传输
```

Claude Desktop（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "zhipu-vision": {
      "command": "python",
      "args": ["<绝对路径>/scripts/mcp_server.py"],
      "env": { "ZHIPU_API_KEY": "你的Key" }
    }
  }
}
```

Cursor：Settings → MCP → Add MCP Server，command 填 `python`，args 填 `mcp_server.py` 绝对路径。

## 缓存

- 默认位置：`~/.codex/cache/zhipu-vision/cache.json`（可用 `ZHIPU_CACHE_FILE` 覆盖）
- 本地图片按内容哈希：同路径文件被替换会自动重新分析；URL 按地址缓存，内容更新需 `--no-cache`
- 清理：删除缓存文件，或运行加 `--no-cache`

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 启动无输出、退出码 9009 | `python` 是 Windows 商店占位符；用 `analyze_image.cmd` 或设置 `ZHIPU_PYTHON` |
| 未找到 API Key | 运行 `setup.py`，或设置环境变量 |
| 400 / 1210 参数有误 | 通常是图片体积/分辨率/格式问题；报错会附图片尺寸；仍失败检查图片是否损坏 |
| 429 / 401 | 限流（脚本自动重试）/ Key 无效，到 bigmodel.cn 检查 |
| 中文路径经管道传 Python 变 `??` | 把脚本写成 .py 文件再执行，或用环境变量传路径 |
| 文档乱码 | 文件为 UTF-8，用 `Get-Content -Encoding UTF8` 读取 |

## 安全

- 仓库**不含真实 API Key**：`.env` 已被 `.gitignore` 忽略，仅提交 `.env.example` 占位模板
- 图片仅以 base64 发送给智谱接口，不保存、不上传第三方
- 模型输出是"解读"而非事实：关键细节以 `--pixel-check` 像素基准为准，实体识别结论需人工/网络核验

## License

MIT
