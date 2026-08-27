"""M4 · RAG 检索问答 Eval（TG-4）。

用合成纪要与确定性哈希向量评估检索命中率（不依赖真实 embedding API，可离线复现）：
- 向量检索：question → 哈希向量 → 余弦 top-k，判定 golden_task_id 是否命中。
- 关键词检索：keyword → minutes 表 LIKE，判定 golden_task_id 是否命中。

用法：
    python scripts/eval_rag.py [--top-k 3]

命中率口径：top-k 中是否包含 golden_task_id（黄金来源）。生产以真实纪要 + bge-m3 替换合成种子。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, rag  # noqa: E402
from app.embedding import chunk_text  # noqa: E402

EVAL_FILE = Path(__file__).resolve().parent.parent / "eval" / "rag_eval.json"
DIM = 256


# --------------------------------------------------------------------------- 确定性哈希向量
def _hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for ch in text:
        h = int(hashlib.md5(ch.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    for i in range(len(text) - 1):
        h = int(hashlib.md5(text[i:i + 2].encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# --------------------------------------------------------------------------- 合成纪要种子
SEED_MINUTES = {
    "prod-001": "产品评审会。决定上线 2.0 版本，灰度发布时间定在下周三。用户反馈最多的功能问题是登录缓慢。遗留埋点需求由张三跟进。",
    "tech-001": "技术架构例会。缓存方案选用 Redis Cluster，消息队列定为 Kafka。数据库迁移由李四牵头，灰度方案待确认。",
    "weekly-001": "项目周会。本周完成登录与支付两个里程碑。联调环境由王五搭建。下周优先级最高的是支付压测。风险：人手不足。",
    "customer-001": "客户需求对接。核心诉求是多租户隔离。报价方案由赵六负责，交付时间节点为下月底。合同条款待法务确认。",
    "budget-001": "预算评审。总预算审批通过 500 万，砍掉办公装修支出。成本核算由孙七负责，下一财年目标营收翻倍。",
    "hiring-001": "招聘复盘。决定录用候选人陈八。发 offer 由周九负责，入职时间定在两周后。背调结果待确认。",
}


def seed(tmp_db: Path) -> None:
    db.init_db(db_path=tmp_db)
    for task_id, content in SEED_MINUTES.items():
        db.save_minute(task_id, title=task_id, summary_md=content,
                       structured_json="{}", user_id="eval-user", db_path=tmp_db)
        chunks = chunk_text(content, size=50, overlap=0)
        db.replace_embeddings(
            task_id, "eval-user",
            [{"text": c, "vector": _hash_embed(c)} for c in chunks],
            db_path=tmp_db)


def main() -> int:
    p = argparse.ArgumentParser(description="RAG 检索命中率 Eval")
    p.add_argument("--top-k", type=int, default=3)
    args = p.parse_args()

    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="rag-eval-")) / "mma.db"
    seed(tmp)

    vector_hits = keyword_hits = 0
    details = []
    for c in cases:
        qvec = _hash_embed(c["question"])
        vhits = rag.retrieve(qvec, "eval-user", args.top_k, db_path=tmp)
        v_ok = any(h["task_id"] == c["golden_task_id"] for h in vhits)
        vector_hits += v_ok

        khits = db.search_minutes(q=c["keyword"], user_id="eval-user", db_path=tmp)[:args.top_k]
        k_ok = any(h["task_id"] == c["golden_task_id"] for h in khits)
        keyword_hits += k_ok

        details.append({
            "question": c["question"],
            "golden_task_id": c["golden_task_id"],
            "vector_top_hits": [h["task_id"] for h in vhits],
            "vector_hit": v_ok,
            "keyword_hit": k_ok,
        })

    total = len(cases)
    report = {
        "total": total,
        "top_k": args.top_k,
        "vector_hit_rate": round(vector_hits / total, 4),
        "keyword_hit_rate": round(keyword_hits / total, 4),
        "details": details,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n向量检索命中率 {report['vector_hit_rate']*100:.1f}%  |  "
          f"关键词检索命中率 {report['keyword_hit_rate']*100:.1f}%  (top-{args.top_k}, N={total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
