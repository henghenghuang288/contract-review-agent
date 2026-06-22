"""
LLM 客户端封装

复用第一个项目(doc-qa-agent)验证过的设计理念:厂商中立 + 优雅降级。
  - 配置 DEEPSEEK_API_KEY  -> DeepSeek(支付宝充值,中文好,性价比高)
  - 配置 OPENAI_API_KEY    -> OpenAI 或自定义 base_url(可指向客户内网自建开源模型)
  - 都没有                 -> 离线模拟模式:用规则生成占位结果,让整个多 Agent 流程在无 key 时也能完整演示

这里所有调用都是异步的(AsyncOpenAI),因为多 Agent 流程中多个 Agent 可以并发执行,
同步客户端会让并发退化成串行,白白浪费等待时间。
"""

import os
from typing import Any


def get_llm_config() -> dict[str, Any] | None:
    """返回当前可用的 LLM 配置,没有任何 key 时返回 None(触发离线模拟模式)。"""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return {"api_key": os.environ["DEEPSEEK_API_KEY"], "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat", "provider": "deepseek"}
    if os.environ.get("OPENAI_API_KEY"):
        base_url = os.environ.get("OPENAI_BASE_URL")
        return {"api_key": os.environ["OPENAI_API_KEY"], "base_url": base_url,
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "provider": "local_model" if base_url else "openai"}
    return None


def is_live() -> bool:
    return get_llm_config() is not None


async def call_llm(system: str, user: str, max_tokens: int = 1200) -> dict[str, Any]:
    """调用大模型,返回 {text, usage, provider}。无 key 时由上层走离线模拟,不会调到这里。"""
    from openai import AsyncOpenAI

    cfg = get_llm_config()
    if cfg is None:
        raise RuntimeError("未配置任何 LLM API Key")

    client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"]) if cfg["base_url"] else AsyncOpenAI(api_key=cfg["api_key"])
    resp = await client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    usage = resp.usage
    return {
        "text": resp.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        } if usage else None,
        "provider": cfg["provider"],
    }
