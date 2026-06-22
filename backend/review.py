"""
合同/条款 风险审查

场景:企业法务或业务方拿到一份合同/协议/条款文档,想快速过一遍,知道:
  - 哪些条款有风险、风险多高
  - 风险点具体在哪、为什么
  - 该怎么改

流程:
  1. 把文档按条款切分(按编号、换行等启发式规则,中文合同常见"第X条""1." 这类编号)
  2. 逐条送给 LLM 审查,要求输出:风险等级(高/中/低/无)、风险说明、修改建议
  3. 汇总成一份结构化报告,按风险等级排序,高风险排前面

与另外两个项目的区别:
  - doc-qa-agent:基于文档"问答"
  - ecom-agent-crew:多角色"协作生成"
  - 本项目:对文档逐条"审查与风险标记"——是第三种 Agent 应用形态(评估/审计型)

防过度判断的设计:明确要求 LLM 只基于条款本身的文字判断,不臆测合同外的背景;
拿不准的标"中"而不是"高",避免制造不必要的恐慌——这对法务工具很重要,
误报高风险会让使用者失去信任。

无 API Key 时走离线模拟:用关键词规则做一个简化版风险标记,让整条流程在无 key 时也能演示。
"""

import asyncio
import json
import re
import time
from typing import Any

from .llm_client import call_llm, is_live

CLAUSE_SYSTEM = (
    "你是一名严谨的合同审查助手。用户会给你合同中的一条条款。请只基于这条条款的文字本身审查风险,"
    "不要臆测合同之外的背景信息。判断要克制:拿不准的标为'中'而不是'高',避免制造不必要的恐慌。"
    "只输出一个 JSON 对象(不要 markdown 代码块标记),字段:"
    "risk_level(字符串,取值:高/中/低/无), issue(字符串,这条条款存在什么风险或问题,无风险则简述其作用), "
    "suggestion(字符串,修改或注意建议,无风险可写'无需修改')。"
)

RISK_ORDER = {"高": 0, "中": 1, "低": 2, "无": 3}


def split_clauses(text: str) -> list[str]:
    """把合同文本按条款切分。优先按'第X条'/'X.'这类编号切,切不出来就按段落(空行)切。"""
    text = text.strip()
    if not text:
        return []

    # 尝试按"第X条"切
    parts = re.split(r"(?=第[一二三四五六七八九十百\d]+条)", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts

    # 尝试按"数字." 或 "数字、" 开头的编号切
    parts = re.split(r"(?=^\s*\d+[.、])", text, flags=re.MULTILINE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts

    # 都不行,按空行分段
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts or [text]


# ---------- 离线模拟:无 key 时用关键词规则做简化风险标记 ----------

_HIGH_RISK_KW = ["无限责任", "不可撤销", "概不退还", "最终解释权", "有权单方", "无条件", "放弃一切", "全部损失由"]
_MID_RISK_KW = ["违约金", "赔偿", "解除", "保密", "知识产权", "自动续约", "滞纳金", "管辖"]


def _offline_review_clause(clause: str) -> dict:
    for kw in _HIGH_RISK_KW:
        if kw in clause:
            return {"risk_level": "高", "issue": f"条款含'{kw}'类表述,可能对一方明显不利或加重责任(离线规则初判)。",
                    "suggestion": "建议法务重点复核该表述的合理性与对等性。", "_offline": True}
    for kw in _MID_RISK_KW:
        if kw in clause:
            return {"risk_level": "中", "issue": f"条款涉及'{kw}',属需关注事项,具体风险取决于约定细节(离线规则初判)。",
                    "suggestion": "建议确认约定是否对等、金额/期限是否合理。", "_offline": True}
    return {"risk_level": "低", "issue": "未命中明显风险关键词,属常规条款(离线规则初判)。",
            "suggestion": "无需特别修改,正式审查建议开启智能模式。", "_offline": True}


# ---------- 单条审查 ----------

async def _review_one(idx: int, clause: str) -> dict[str, Any]:
    if not is_live():
        result = _offline_review_clause(clause)
        return {"index": idx, "clause": clause, **result, "usage": None}

    t0 = time.perf_counter()
    res = await call_llm(CLAUSE_SYSTEM, clause, max_tokens=600)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    cleaned = res["text"].replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {"risk_level": "中", "issue": "解析模型输出失败,建议人工复核此条。", "suggestion": "人工复核"}
    return {"index": idx, "clause": clause, **parsed, "usage": res["usage"], "latency_ms": latency_ms}


# ---------- 整篇审查 ----------

async def review_contract(text: str) -> dict[str, Any]:
    request_t0 = time.perf_counter()
    clauses = split_clauses(text)

    if not clauses:
        return {"mode": "offline_simulation" if not is_live() else "live", "clauses_count": 0,
                "findings": [], "summary": {"高": 0, "中": 0, "低": 0, "无": 0},
                "total_latency_ms": 0, "total_tokens": None}

    # 各条款相互独立,可以并发审查(这里是真实的并发场景,不是伪造的)
    # ——和 ecom 项目的顺序依赖链不同,合同条款之间没有依赖,所以用 asyncio.gather 并发能真正提速
    findings = await asyncio.gather(*[_review_one(i + 1, c) for i, c in enumerate(clauses)])

    # 按风险等级排序,高风险排前
    findings_sorted = sorted(findings, key=lambda f: RISK_ORDER.get(f.get("risk_level", "中"), 1))

    summary = {"高": 0, "中": 0, "低": 0, "无": 0}
    total_tokens = 0
    for f in findings:
        lvl = f.get("risk_level", "中")
        summary[lvl] = summary.get(lvl, 0) + 1
        if f.get("usage") and f["usage"].get("total_tokens"):
            total_tokens += f["usage"]["total_tokens"]

    return {
        "mode": "offline_simulation" if not is_live() else "live",
        "clauses_count": len(clauses),
        "findings": findings_sorted,
        "summary": summary,
        "total_latency_ms": round((time.perf_counter() - request_t0) * 1000, 1),
        "total_tokens": total_tokens or None,
    }
