#!/usr/bin/env python3
"""用智谱免费视觉模型分析图片并返回文字描述。

用法:
    python analyze_image.py <图片路径或URL> ["问题"]
                           [--detail brief|standard|detailed]
                           [--language zh|en|auto]
                           [--thinking]
                           [--show-reasoning]
                           [--verify]
                           [--no-cache] [--cache-age DAYS]
                           [--save-preview PATH]

功能:
    - 超过 10MB 或格式不支持的本地图片，若安装 Pillow 则自动压缩/转换为 JPEG
    - 相机 RAW（ARW/CR2/NEF 等）自动扫描文件内 JPEG 段并取最大者
    - 本地结果缓存（默认 30 天，按图片内容+提示词哈希），--no-cache 跳过
    - --verify 两轮独立描述：第二轮强制重新枚举、标注【不确定】细节，
      并用特征词表做程序化对比，标记两轮差异
    - --pixel-check 用 Pillow 做像素级采样（ASCII 字符画+颜色网格），
      作为与模型描述对照的独立基准
    - 识别类问题（"是什么App"等）自动注入"无法确定时必须明说"的约束

环境变量:
    ZHIPU_API_KEY   智谱 API Key（必填；未设置时读取技能目录下的 .env）
    ZHIPU_MODEL     主模型 ID（默认 glm-4.6v-flash）
    ZHIPU_BASE_URL  接口基础地址（默认 https://open.bigmodel.cn/api/paas/v4）
    ZHIPU_CACHE_FILE 缓存文件路径（默认 ~/.codex/cache/zhipu-vision/cache.json）
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 非 UTF-8 控制台下避免中文输出崩溃：无法编码的字符用 ? 替代
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
DEFAULT_MODEL = "glm-4.6v-flash"
FALLBACK_MODELS = ("glm-4v-flash", "glm-4.1v-thinking-flash")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 2048  # 最长边防御性上限：压缩/缩放后载荷降到 1-3MB，避开接口体积边缘问题
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
RAW_EXTENSIONS = {".arw", ".cr2", ".cr3", ".dng", ".nef", ".nrw", ".orf", ".pef", ".raf", ".rw2", ".srw", ".raw"}
DEFAULT_CACHE_AGE_DAYS = 30
SCRIPT_DIR = Path(__file__).resolve().parent

_cache_env = os.environ.get("ZHIPU_CACHE_FILE", "").strip()
_codex_home = os.environ.get("CODEX_HOME", "").strip()
_default_cache_root = Path(_codex_home) if _codex_home else Path.home() / ".codex"
CACHE_FILE = Path(_cache_env) if _cache_env else (
    _default_cache_root / "cache" / "zhipu-vision" / "cache.json"
)


def load_api_key() -> str:
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if key:
        return key
    env_file = SCRIPT_DIR.parent / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ZHIPU_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit(
        "错误: 未找到 ZHIPU_API_KEY。\n"
        "最简单的方式：运行一键配置脚本 python scripts/setup.py，按提示粘贴 Key 即可。\n"
        "也可以二选一：\n"
        "  1) 设置环境变量: set ZHIPU_API_KEY=你的Key（PowerShell）\n"
        "  2) 复制技能目录下的 .env.example 为 .env，把 ZHIPU_API_KEY 改成你的 Key\n"
        "Key 免费申请地址: https://open.bigmodel.cn"
    )


def _downscale_compress(img) -> tuple[bytes, str] | None:
    """统一缩放+压缩：最长边 ≤MAX_IMAGE_SIDE，JPEG 质量阶梯压缩到 ≤10MB。"""
    from PIL import Image
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_IMAGE_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    for quality in (85, 75, 60, 45, 30):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            return data, "image/jpeg"
    return None


def _auto_preprocess(path: Path) -> tuple[bytes, str] | None:
    """用 Pillow 把图片转 JPEG 并压缩到 ≤10MB；Pillow 缺失或解码失败返回 None。"""
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.load()
            return _downscale_compress(img)
    except Exception:
        return None


def _extract_embedded_jpeg(path: Path) -> bytes | None:
    """从相机 RAW 中提取最大的内嵌 JPEG 预览（扫描 FFD8..FFD9 段）。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    candidates: list[bytes] = []
    start = 0
    while True:
        soi = data.find(b"\xff\xd8", start)
        if soi == -1:
            break
        eoi = data.find(b"\xff\xd9", soi + 2)
        if eoi == -1:
            break
        blob = data[soi : eoi + 2]
        if len(blob) > 4096:  # 过滤过小的缩略图
            candidates.append(blob)
        start = eoi + 2
    return max(candidates, key=len) if candidates else None


def _jpeg_to_ref(data: bytes) -> str:
    """JPEG 字节转 data URL；超限时尝试缩放压缩。"""
    if len(data) > MAX_IMAGE_BYTES:
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                down = _downscale_compress(img)
            if down:
                data, _ = down
        except Exception:
            pass
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _exceeds_max_side(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as img:
            return max(img.size) > MAX_IMAGE_SIDE
    except Exception:
        return False


def to_image_ref(image: str, save_preview: str = "") -> str:
    if image.startswith(("http://", "https://", "data:")):
        return image
    path = Path(image).expanduser()
    if not path.is_file():
        raise SystemExit(f"错误: 图片文件不存在: {image}")
    if path.suffix.lower() in RAW_EXTENSIONS:
        preview = _extract_embedded_jpeg(path)
        if preview is None:
            raise SystemExit(
                f"错误: 相机 RAW 格式 {path.suffix or '(未知)'} 不支持直接解码，"
                "且未扫描到可用 JPEG 段。请先转换为 JPEG/PNG 再分析。"
            )
        if save_preview:
            try:
                out_path = Path(save_preview).expanduser()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(preview)
                print(f"预览图已保存: {out_path}")
            except OSError as exc:
                print(f"警告: 预览图保存失败: {exc}")
        return _jpeg_to_ref(preview)
    size = path.stat().st_size
    ext_ok = path.suffix.lower() in SUPPORTED_EXTENSIONS
    too_large = size > MAX_IMAGE_BYTES
    too_big_side = _exceeds_max_side(path)
    if not too_large and ext_ok and not too_big_side:
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    pre = _auto_preprocess(path)
    if pre is None:
        reasons = []
        if too_large:
            reasons.append(f"图片超过 10MB（{size} 字节）")
        if too_big_side:
            reasons.append("最长边超过 2048px")
        if not ext_ok:
            reasons.append(f"不支持的图片格式 {path.suffix or '(无扩展名)'}")
        raise SystemExit(
            f"错误: {'、'.join(reasons)}，且自动转换失败（需要 Pillow 且图片可解码）。"
            "请安装 Pillow 或手动压缩/转换为 jpg/png 后重试。"
        )
    data, mime = pre
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def call_glm(
    api_key: str, image_ref: str, prompt: str, thinking: bool, image_hint: str = ""
) -> tuple[str, str]:
    models = [os.environ.get("ZHIPU_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL, *FALLBACK_MODELS]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error = ""

    for model in models:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_ref}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        if thinking:
            payload["thinking"] = {"type": "enabled"}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{BASE_URL}/chat/completions", data=body, headers=headers, method="POST"
        )

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    message = data["choices"][0]["message"]
                    content = (message.get("content") or "").strip()
                    reasoning = (message.get("reasoning_content") or "").strip()
                    return content, reasoning
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", "replace")[:300]
                if exc.code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                if exc.code in (400, 404) and "model" in error_body.lower():
                    last_error = f"模型 {model} 不可用: {error_body}"
                    break
                if exc.code == 400:
                    raise SystemExit(
                        f"错误: 智谱 API 返回 400: {error_body}\n"
                        f"提示: 400/1210 通常是图片参数问题（体积/分辨率/格式）。{image_hint}"
                        "脚本已自动把图片压缩到 ≤10MB 且最长边 ≤2048px；若仍失败请检查图片是否损坏。"
                    )
                raise SystemExit(f"错误: 智谱 API 返回 {exc.code}: {error_body}")
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = str(exc)
                time.sleep(1)
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                raise SystemExit(f"错误: 无法解析智谱 API 响应: {exc}")

    raise SystemExit(f"错误: 智谱 API 调用失败: {last_error}")


def _load_cache() -> dict:
    try:
        if CACHE_FILE.is_file():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _prune_cache(cache: dict, max_age_days: int) -> None:
    cutoff = time.time() - max_age_days * 86400
    for key in [k for k, v in cache.items() if v.get("ts", 0) < cutoff]:
        del cache[key]


def _cache_key(image_ref: str, prompt: str, thinking: bool) -> str:
    digest = hashlib.sha256()
    digest.update(image_ref.encode("utf-8"))
    digest.update(b"\n")
    digest.update(prompt.encode("utf-8"))
    digest.update(f"\nthinking={thinking}".encode("ascii"))
    return digest.hexdigest()


def run_pass(
    api_key: str,
    image_ref: str,
    prompt: str,
    thinking: bool,
    use_cache: bool,
    cache_age_days: int,
    image_hint: str = "",
) -> tuple[str, str, bool]:
    key = _cache_key(image_ref, prompt, thinking)
    if use_cache:
        cache = _load_cache()
        entry = cache.get(key)
        if entry:
            return entry.get("content", ""), entry.get("reasoning", ""), True
    content, reasoning = call_glm(api_key, image_ref, prompt, thinking, image_hint)
    if use_cache:
        cache = _load_cache()
        _prune_cache(cache, cache_age_days)
        cache[key] = {"ts": time.time(), "content": content, "reasoning": reasoning}
        _save_cache(cache)
    return content, reasoning, False


DETAIL_PROMPTS = {
    "brief": "用一句话简要概括图片内容。",
    "standard": "请简洁描述这张图片：主体、颜色、布局、文字（如有）。",
    "detailed": "请非常详细地描述这张图片：主体、背景、颜色、布局、文字、风格、可能用途等，尽量完整。",
}
DETAIL_REQUIRED_KEYWORDS = ("提取", "所有", "全部", "详细", "完整", "列出", "每一", "逐个", "全文", "所有文字")
LANGUAGE_PROMPTS = {
    "zh": "请使用中文回答。",
    "en": "Please answer in English.",
    "auto": "",
}
VERIFY_PROMPT = (
    "请重新、独立地描述这张图片，从零开始逐项枚举所有元素。"
    "逐项说明颜色、形状、方向、数量、文字（如有）。"
    "对你不确定或无法确认的细节，标注【不确定】并说明原因。"
    "先给结论，再列出【细节清单】。"
)

# 像素采样结果作为事实基准注入提示词：把"观察"和"推断"在结构上分开，
# 避免模型把无像素依据的具体名称/归属混进描述当事实。
PIXEL_GROUNDING = (
    "以下是程序化像素采样结果（非模型输出，可作为事实基准）：\n{baseline}\n\n"
    "请基于上述像素事实描述图片。像素采样无法证实的具体名称、年代、归属等判断"
    "属于推测，请在末尾单独列出【推测】段落并说明依据不足。"
)

ENTITY_KEYWORDS = (
    "是什么", "哪个", "什么App", "什么应用", "什么软件", "什么网站",
    "什么游戏", "哪款", "品牌", "识别这是什么", "这是什么",
)
# 识别任务的结构化改写：不索取唯一答案，改为“候选假设+依据”，
# 从任务设计上避免模型把单个猜测包装成事实。
IDENTIFY_FRAMING = (
    "这是一个识别任务：请先完整描述图片的结构、颜色、文字（如有），"
    "然后列出 2-5 个最可能的具体实体候选（应用/网站/品牌等），"
    "逐个说明判断依据和依据强度，不要只给一个答案。"
)
CONFIRMATION_MARKERS = (
    "与上一轮一致", "和上一轮一致", "与第一轮一致", "和第一轮一致",
    "同上", "无差异", "没有差异", "和之前一致", "与之前一致",
)

FEATURE_LEXICON = {
    "颜色": ["红", "橙", "黄", "绿", "蓝", "紫", "粉", "黑", "白", "灰", "棕", "金", "银", "青"],
    "形状": ["圆", "方", "三角", "矩形", "椭圆", "箭头", "星", "心", "十字", "圆圈", "方块"],
    "对象": ["狗", "猫", "鸟", "飞机", "车", "人", "树", "花", "房子", "手机", "表", "杯"],
    "方向": ["左", "右", "上", "下", "中", "角", "顶", "底", "侧"],
}


def build_prompt(question: str, detail: str, language: str) -> str:
    parts = []
    if question.strip():
        parts.append(question.strip())
    if (
        detail == "standard"
        and question.strip()
        and any(kw in question for kw in DETAIL_REQUIRED_KEYWORDS)
    ):
        detail = "detailed"  # 提取/穷尽类任务自动升级为详细模式，避免漏细节
    parts.append(DETAIL_PROMPTS[detail])
    if question.strip() and any(kw in question for kw in ENTITY_KEYWORDS):
        parts.append(IDENTIFY_FRAMING)
    if LANGUAGE_PROMPTS[language]:
        parts.append(LANGUAGE_PROMPTS[language])
    return "\n".join(parts)


def _is_confirmation(text: str) -> bool:
    return any(marker in text for marker in CONFIRMATION_MARKERS)


def _extract_features(text: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for category, words in FEATURE_LEXICON.items():
        found[category] = {w for w in words if w in text}
    return found


def feature_diff_section(text1: str, text2: str) -> str:
    """基于特征词表的程序化对比，输出两轮描述在颜色/形状/对象/方向上的差异。"""
    f1, f2 = _extract_features(text1), _extract_features(text2)
    lines = ["[程序化对比]（基于特征词表，粗粒度、非语义判断）"]
    diff_count = 0
    for category in FEATURE_LEXICON:
        both = sorted(f1[category] & f2[category])
        only1 = sorted(f1[category] - f2[category])
        only2 = sorted(f2[category] - f1[category])
        if only1 or only2:
            diff_count += 1
        lines.append(
            f"{category}: 两轮共有 [{', '.join(both) or '无'}]"
            f"；仅第一轮 [{', '.join(only1) or '无'}]"
            f"；仅第二轮 [{', '.join(only2) or '无'}]"
        )
    if diff_count == 0:
        lines.append(
            "结论: 词表级无差异。注意两轮词表完全一致可能只是复述，"
            "不代表绝对正确，也不代表第二轮真的重新描述过；建议人工确认。"
        )
    else:
        lines.append(
            f"结论: 检测到 {diff_count} 类特征差异，相关细节以 --pixel-check 的像素结果为准，"
            "不要仅凭两轮描述判定。"
        )
    return "\n".join(lines)


def _nearest_color(r: int, g: int, b: int) -> str:
    palette = {
        "黑": (0, 0, 0), "白": (255, 255, 255), "灰": (128, 128, 128),
        "红": (220, 30, 30), "橙": (240, 140, 30), "黄": (240, 220, 40),
        "绿": (40, 180, 60), "青": (40, 190, 190), "蓝": (30, 80, 220),
        "紫": (140, 60, 200), "粉": (230, 120, 160), "棕": (130, 80, 40),
    }
    return min(palette, key=lambda name: sum((palette[name][i] - c) ** 2 for i, c in enumerate((r, g, b))))


def pixel_check(image_path: str) -> str:
    """用 Pillow 输出分区颜色网格和主色统计，作为独立于视觉模型的像素级基准。"""
    try:
        from PIL import Image
    except ImportError:
        return "错误: --pixel-check 需要 Pillow，请先执行 pip install pillow"
    path = Path(image_path).expanduser()
    if not path.is_file():
        return f"错误: 图片文件不存在: {image_path}"
    try:
        with Image.open(path) as img:
            img.load()
            grid = img.convert("RGB").resize((16, 8))
            grid_lines = []
            color_counts: dict[str, int] = {}
            for y in range(8):
                row = []
                for x in range(16):
                    r, g, b = grid.getpixel((x, y))
                    name = _nearest_color(r, g, b)
                    row.append(name)
                    color_counts[name] = color_counts.get(name, 0) + 1
                grid_lines.append(f"行{y + 1}: " + " ".join(row))
            total = 16 * 8
            top = sorted(color_counts.items(), key=lambda kv: -kv[1])[:6]
            summary = "，".join(f"{name} {count * 100 // total}%" for name, count in top)
    except Exception as exc:
        return f"错误: 像素采样失败: {exc}"
    return (
        "===== 像素级采样（Pillow，独立基准）=====\n"
        "主色统计（16x8 采样）: " + summary + "\n\n"
        "分区颜色网格（每格为区域平均色最近的颜色名，左上角为 行1列1）:\n"
        + "\n".join(grid_lines)
        + "\n\n说明: 以上是程序化采样结果，不是模型输出，可用来对照模型描述。"
    )


def print_result(content: str, reasoning: str, cache_hit: bool, show_reasoning: bool = False) -> None:
    if cache_hit:
        print("(缓存命中)")
    if show_reasoning and reasoning:
        print(f"[思考过程]\n{reasoning}\n")
    print(content or "(模型未返回内容)")


def main() -> int:
    parser = argparse.ArgumentParser(description="用智谱免费视觉模型分析图片")
    parser.add_argument("image", help="本地图片路径或 http(s) URL")
    parser.add_argument("question", nargs="?", default="", help="针对图片的具体问题或指令")
    parser.add_argument("--detail", choices=DETAIL_PROMPTS.keys(), default="standard", help="详细程度")
    parser.add_argument("--language", choices=LANGUAGE_PROMPTS.keys(), default="auto", help="回答语言")
    parser.add_argument("--thinking", action="store_true", help="开启深度思考")
    parser.add_argument("--show-reasoning", action="store_true", help="打印模型思考过程（默认不打印以省 token）")
    parser.add_argument("--verify", action="store_true", help="两轮独立描述+程序化对比")
    parser.add_argument("--pixel-check", action="store_true", help="输出像素级采样作为独立基准")
    parser.add_argument("--save-preview", default="", help="把 RAW 提取出的 JPEG 预览保存到指定路径")
    parser.add_argument("--no-cache", action="store_true", help="跳过本地缓存")
    parser.add_argument("--cache-age", type=int, default=DEFAULT_CACHE_AGE_DAYS, help="缓存有效期（天）")
    args = parser.parse_args()

    api_key = load_api_key()
    image = to_image_ref(args.image, args.save_preview)
    use_cache = not args.no_cache
    is_identify = bool(args.question.strip() and any(kw in args.question for kw in ENTITY_KEYWORDS))

    image_hint = ""
    if not args.image.startswith(("http://", "https://", "data:")):
        local_path = Path(args.image).expanduser()
        if local_path.is_file():
            hint_parts = [f"图片字节数 {local_path.stat().st_size}"]
            try:
                from PIL import Image as PILImage
                with PILImage.open(local_path) as im:
                    hint_parts.append(f"尺寸 {im.size[0]}x{im.size[1]}")
            except Exception:
                pass
            image_hint = "，".join(hint_parts) + "。"

    baseline = ""
    if args.pixel_check or is_identify:
        if args.image.startswith(("http://", "https://", "data:")):
            print("注意: 像素采样仅支持本地文件，URL 输入跳过（识别任务建议先下载到本地再核验）。")
        else:
            baseline = pixel_check(args.image)
            print(baseline)
            print()

    prompt = build_prompt(args.question, args.detail, args.language)
    if baseline:
        prompt = PIXEL_GROUNDING.format(baseline=baseline) + "\n\n" + prompt

    if args.verify:
        c1, r1, h1 = run_pass(api_key, image, prompt, args.thinking, use_cache, args.cache_age, image_hint)
        c2, r2, h2 = run_pass(api_key, image, VERIFY_PROMPT, args.thinking, use_cache, args.cache_age, image_hint)
        print("===== 第一轮描述 =====")
        print_result(c1, r1, h1, args.show_reasoning)
        print("\n===== 第二轮核对 =====")
        print_result(c2, r2, h2, args.show_reasoning)
        print()
        print(feature_diff_section(c1 or "", c2 or ""))
        if _is_confirmation(c2 or ""):
            print("\n⚠ 第二轮检出确认性表述（如“与上一轮一致”），疑似未真正重新描述；"
                  "以上对比降级，判定以像素采样为准。")
        print(
            "\n===== 置信度提示 =====\n"
            "两轮一致≠正确；差异以像素采样为准。"
            "实体识别结论无标志性特征佐证时视为推测，需核验。"
        )
    else:
        content, reasoning, hit = run_pass(
            api_key, image, prompt, args.thinking, use_cache, args.cache_age, image_hint
        )
        print_result(content, reasoning, hit, args.show_reasoning)
    if is_identify:
        print(
            "\n===== 识别结论（脚本判定）=====\n"
            "候选仅为假设；默认结论“无法确认/识别未完成”，需人工或网络核验。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
