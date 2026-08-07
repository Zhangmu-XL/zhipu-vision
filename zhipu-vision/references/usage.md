# 详细使用说明（按需加载）

## 参数

| 参数 | 说明 |
| --- | --- |
| `image` | 本地图片路径或 http(s) URL；≤10MB 且最长边 ≤2048px，超出自动压缩/缩放；相机 RAW（ARW/CR2/NEF 等）自动扫描文件内 JPEG 段并取最大者（相机内嵌预览或已处理 JPEG） |
| `question` | 针对图片的问题/指令 |
| `--detail brief\|standard\|detailed` | 详细程度，默认 standard |
| `--language auto\|zh\|en` | 回答语言，默认 auto |
| `--thinking` | 开启深度思考 |
| `--show-reasoning` | 打印模型思考过程（默认不打印以省 token） |
| `--verify` | 两轮独立描述+特征词表程序化对比；第二轮检出确认性表述会标记降级 |
| `--pixel-check` | 像素级采样（分区颜色网格+主色统计），注入提示词作事实基准（需 Pillow，仅本地图） |
| `--save-preview PATH` | 把 RAW 提取出的 JPEG 预览保存到指定路径（方便目视核验/分享） |
| `--no-cache` | 跳过本地缓存 |
| `--cache-age DAYS` | 缓存有效期，默认 30 天 |

## 示例

```powershell
& "scripts\analyze_image.cmd" "D:\photo.jpg" "提取图中所有文字"
& "scripts\analyze_image.cmd" "https://example.com/a.png" --detail detailed --language zh
& "scripts\analyze_image.cmd" "D:\icon.png" "这是什么 App？" --pixel-check --verify
python3 scripts/analyze_image.py "D:\photo.jpg" --show-reasoning
& "scripts\analyze_image.cmd" "D:\DSC01668.ARW" "描述" --save-preview "D:\preview.jpg"
```

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `ZHIPU_API_KEY` | 是 | 智谱 API Key，申请地址 open.bigmodel.cn |
| `ZHIPU_MODEL` | 否 | 主模型 ID，默认 `glm-4.6v-flash` |
| `ZHIPU_BASE_URL` | 否 | 接口基础地址，默认 `https://open.bigmodel.cn/api/paas/v4` |
| `ZHIPU_CACHE_FILE` | 否 | 缓存文件路径，默认 `~/.codex/cache/zhipu-vision/cache.json` |
| `ZHIPU_PYTHON` | 否 | 仅 Windows 启动器：显式指定 Python 解释器绝对路径（通常无需设置） |

## 手动配置 API Key

1. 环境变量：`$env:ZHIPU_API_KEY = "你的Key"`（PowerShell）/ `export ZHIPU_API_KEY=你的Key`（bash）
2. 复制 `.env.example` 为 `.env` 并填入 Key（`.env` 已被 .gitignore 忽略）

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 启动无输出、退出码 9009 | `python` 是商店占位符；用启动器或设 `ZHIPU_PYTHON` |
| 启动器报未找到 Python | 已自动探测常见目录和 Codex 运行时；仍失败则装 Python 或设 `ZHIPU_PYTHON` |
| 未找到 ZHIPU_API_KEY | 运行 `setup.py`，或见上"手动配置" |
| 图片过大/格式/分辨率超限 | 自动压缩/缩放为 JPEG（需 Pillow）；失败才手动处理 |
| 相机 RAW（ARW/CR2/NEF）不识别 | 自动扫描文件内 JPEG 段并取最大者；扫描失败时请先转换为 JPEG/PNG |
| 想拿到 RAW 的预览图 | 加 `--save-preview 输出路径`，脚本会把提取出的 JPEG 落盘 |
| 400 / 1210 参数有误 | 通常是图片体积/分辨率/格式问题；报错附字节数与尺寸；仍失败检查图片是否损坏 |
| 429 | 限流，脚本自动重试；稍后再试 |
| 401 | Key 无效或复制不完整 |
| 清理缓存 | 删除 `~/.codex/cache/zhipu-vision/cache.json` 或加 `--no-cache` |
| 文档乱码 | 文件是 UTF-8，用 `Get-Content -Encoding UTF8` 读取 |
| 中文路径经 PowerShell 管道传给 Python 变成 `??` | 不要用 `python -` 管道传含中文的路径；把脚本写成 .py 文件再执行，或用环境变量传路径 |

## MCP（其他 Agent）

`scripts/mcp_server.py` 暴露 `analyze_image` 工具，参数同上（含 `show_reasoning`）。依赖：`pip install -r requirements-mcp.txt`。

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

Cursor：Settings → MCP → Add MCP Server，command 填 `python`，args 填 `mcp_server.py` 的绝对路径。

## 发布与安全

- 发布 GitHub 前确认不带真实 Key：`.env` 已 gitignore，仓库只提交 `.env.example`
- 脚本只调用文本输出接口，不保存、不上传图片到第三方（base64 仅发智谱接口）
