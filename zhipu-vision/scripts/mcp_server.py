#!/usr/bin/env python3
"""Zhipu Vision MCP 服务器。

让任何支持 MCP 的 Agent（Claude Desktop、Cursor、Cline、Continue 等）
都能调用 analyze_image 工具，复用 analyze_image.py 的全部能力：
缓存、自动压缩转换、像素采样、两轮核对、识别任务结构化解构。

安装依赖:
    pip install "mcp>=1.2.0,<2.0.0"

运行（stdio 传输）:
    python mcp_server.py

客户端配置示例（Claude Desktop 的 claude_desktop_config.json）:
    {
      "mcpServers": {
        "zhipu-vision": {
          "command": "python",
          "args": ["<mcp_server.py 的绝对路径>"]
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import analyze_image as ai

mcp = FastMCP("zhipu-vision")


def _format_pass(content: str, reasoning: str, cache_hit: bool, show_reasoning: bool = False) -> str:
    parts = []
    if cache_hit:
        parts.append("(缓存命中)")
    if show_reasoning and reasoning:
        parts.append(f"[思考过程]\n{reasoning}")
    parts.append(content or "(模型未返回内容)")
    return "\n".join(parts)


@mcp.tool()
def analyze_image(
    image: str,
    question: str = "",
    detail: str = "standard",
    language: str = "auto",
    thinking: bool = False,
    show_reasoning: bool = False,
    verify: bool = False,
    pixel_check: bool = False,
    no_cache: bool = False,
) -> str:
    """用智谱免费视觉模型分析图片并返回文字描述。"""
    try:
        api_key = ai.load_api_key()
        image_ref = ai.to_image_ref(image)
        prompt = ai.build_prompt(question, detail, language)
        use_cache = not no_cache

        sections: list[str] = []
        if pixel_check and not image.startswith(("http://", "https://", "data:")):
            sections.append(ai.pixel_check(image))

        if verify:
            c1, r1, h1 = ai.run_pass(api_key, image_ref, prompt, thinking, use_cache, ai.DEFAULT_CACHE_AGE_DAYS)
            c2, r2, h2 = ai.run_pass(api_key, image_ref, ai.VERIFY_PROMPT, thinking, use_cache, ai.DEFAULT_CACHE_AGE_DAYS)
            sections.append("===== 第一轮描述 =====\n" + _format_pass(c1, r1, h1, show_reasoning))
            sections.append("===== 第二轮核对 =====\n" + _format_pass(c2, r2, h2, show_reasoning))
            sections.append(ai.feature_diff_section(c1 or "", c2 or ""))
            if ai._is_confirmation(c2 or ""):
                sections.append(
                    "⚠ 第二轮检出确认性表述（如“与上一轮一致”），疑似未真正重新描述；"
                    "以上对比降级，判定以像素采样为准。"
                )
            sections.append(
                "===== 置信度提示 =====\n"
                "两轮一致≠正确；差异以像素采样为准。"
                "实体识别结论无标志性特征佐证时视为推测，需核验。"
            )
        else:
            content, reasoning, hit = ai.run_pass(
                api_key, image_ref, prompt, thinking, use_cache, ai.DEFAULT_CACHE_AGE_DAYS
            )
            sections.append(_format_pass(content, reasoning, hit, show_reasoning))

        if question and any(kw in question for kw in ai.ENTITY_KEYWORDS):
            sections.append(
                "===== 识别结论（脚本判定）=====\n"
                "候选仅为假设；默认结论“无法确认/识别未完成”，需人工或网络核验。"
            )
        return "\n\n".join(sections)
    except SystemExit as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
