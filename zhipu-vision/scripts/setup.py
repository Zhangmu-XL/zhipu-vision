#!/usr/bin/env python3
"""一键配置智谱 API Key：验证有效后写入技能目录 .env。

用法:
    python setup.py               # 交互式：按提示粘贴 Key
    python setup.py YOUR_API_KEY  # 非交互式（脚本/CI 友好，Agent 调用请用这种）
    python setup.py --check       # 只验证当前已配置的 Key，不写入

已存在的 .env 中其他配置会被保留。仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 非 UTF-8 控制台下避免中文/符号输出崩溃：无法编码的字符用 ? 替代
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR.parent / ".env"
BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")


def _read_existing_key() -> str:
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ZHIPU_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def validate_key(api_key: str) -> bool:
    """用一次最小文本请求验证 Key 是否有效。"""
    model = os.environ.get("ZHIPU_MODEL", "glm-4-flash").strip() or "glm-4-flash"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            json.loads(response.read().decode("utf-8"))
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("[FAIL] Key 验证失败：无效的 API Key（HTTP 401），请检查是否复制完整。")
            return False
        if exc.code == 429:
            print("[WARN] 验证被限流（429），跳过验证，直接写入。")
            return True
        print(f"[WARN] Key 验证返回 HTTP {exc.code}，跳过验证，直接写入。")
        return True
    except (urllib.error.URLError, OSError, TimeoutError):
        print("[WARN] 网络不可用，跳过验证，直接写入。")
        return True


def write_env(api_key: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    replaced = False
    out = []
    for line in lines:
        if line.strip().startswith("ZHIPU_API_KEY="):
            out.append(f"ZHIPU_API_KEY={api_key}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"ZHIPU_API_KEY={api_key}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="配置智谱 API Key（写入 .env 并验证）")
    parser.add_argument("key", nargs="?", help="API Key；省略则交互式输入")
    parser.add_argument("--check", action="store_true", help="只验证现有 Key，不写入")
    args = parser.parse_args()

    if args.check:
        key = os.environ.get("ZHIPU_API_KEY", "").strip() or _read_existing_key()
        if not key:
            print("未找到已配置的 Key（环境变量或 .env）。")
            return 1
        ok = validate_key(key)
        print("Key 有效 [OK]" if ok else "Key 无效 [FAIL]")
        return 0 if ok else 1

    key = (args.key or os.environ.get("ZHIPU_API_KEY", "")).strip()
    if not key:
        try:
            key = input("请输入智谱 API Key（到 https://open.bigmodel.cn 免费申请）: ").strip()
        except EOFError:
            print("错误: 非交互环境下请用: python setup.py <你的Key>")
            return 1
    if not key:
        print("错误: Key 不能为空。")
        return 1

    if not validate_key(key):
        print("未写入 .env（Key 验证未通过）。")
        return 1
    write_env(key)
    print(f"[OK] 已写入 {ENV_FILE}")
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[HINT] 未安装 Pillow：超过 10MB 或分辨率超限的图片自动压缩/缩放和 --pixel-check 将不可用。")
        print("       建议执行: pip install pillow")
    print("接下来：完全重启 Codex 并新开会话；或参考仓库 README 配置 MCP 客户端。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
