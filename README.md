# Contract Clause Risk Reviewer

> 🇨🇳 [中文版见下方](#中文说明)

Upload a contract, get a structured risk assessment — clause by clause. Each clause is scored High / Medium / Low / None risk with a specific issue description and revision suggestion. High-risk clauses surface first.

**Live demo:** deploy via `render.yaml` or `docker compose up`

## Design Principles

**Parallel by default.** Contract clauses are independent of each other — no clause depends on another's result. Uses `asyncio.gather` to review all clauses concurrently. A 20-clause contract takes roughly the same time as a 1-clause contract.

**Deliberately conservative scoring.** Legal tools that cry wolf lose user trust fast. The system prompt explicitly instructs: base judgment only on the clause text itself (no background assumptions), and when uncertain, mark Medium — not High. Avoiding false alarms is a feature, not a bug.

**Contrast with ecom-agent-crew:** that project uses sequential execution because agents depend on each other. This project uses concurrency because clauses are independent. Same async primitives, opposite architectural choice — driven by dependency structure.

## Offline Mode

Keyword rules handle offline scoring (matches "有权单方", "最终解释权" → High; "违约金", "保密" → Medium). Full semantic judgment requires an API key.

## Stack

Python · FastAPI · asyncio · DeepSeek/OpenAI-compatible · Docker

## Quick Start

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-xxxx   # optional
uvicorn backend.main:app --reload
```

---

## 中文说明

上传合同，逐条审查风险等级，高风险排最前，每条给出风险点和修改建议。

**关键设计：**
- 条款并发审查（asyncio.gather）：合同各条款互相独立，真正可以并发
- 判断克制：拿不准标"中"不标"高"，法务工具不能制造不必要恐慌
- 与电商多Agent项目形成对照：那个有依赖所以顺序，这个独立所以并发
