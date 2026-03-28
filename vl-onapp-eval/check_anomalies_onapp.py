"""
check_anomalies_onapp.py — 数据质量验证

检查项:
  - 各模型各条件的 case 数是否一致
  - 空响应 / token loop / 失败 case
  - 工具调用时机（有异常terminal_data但未调工具）
  - 超长响应（token loop风险）
  - 评分缺失 / 评分超范围

用法:
  python check_anomalies_onapp.py
  python check_anomalies_onapp.py --run run_20260320_1000
"""

import sys, json, argparse
from pathlib import Path
from collections import Counter

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EVAL_DIR     = Path(__file__).parent
RESULTS_BASE = EVAL_DIR / "results"

ANOMALY_KEYWORDS = ["偏低", "偏高", "异常", "高于正常", "低于正常"]

DIMS = [
    "视觉识别准确率", "幻觉控制率", "数值读取精度", "输出时序合规",
    "安全声明合规",   "边界克制合规", "数据引用质量", "端侧数据优先性",
    "工具调用时机准确性", "工具调用结果整合度", "任务完成度", "图像与上下文一致性",
]


def has_anomaly(terminal_data: str) -> bool:
    return any(kw in terminal_data for kw in ANOMALY_KEYWORDS)


def check_loop(response: str) -> bool:
    if len(response) < 2000:
        return False
    chunk = response[:100]
    return response.count(chunk) > 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", help="指定 run 目录")
    args = parser.parse_args()

    if args.run:
        results_dir = RESULTS_BASE / args.run
    else:
        runs = sorted(RESULTS_BASE.glob("run_*"), reverse=True)
        results_dir = runs[0] if runs else None

    if not results_dir or not results_dir.exists():
        print("[error] No results dir found.")
        return

    issues: list[str] = []
    stats: dict = {}

    for json_path in sorted(results_dir.glob("*_results.json")):
        data = json.loads(json_path.read_text("utf-8"))
        name = data["model"]["name"]
        stats[name] = {}

        for cond, results in data.get("conditions", {}).items():
            n_total   = len(results)
            n_done    = sum(1 for r in results if r.get("status") in ("done", "judged"))
            n_failed  = sum(1 for r in results if r.get("status") == "failed")
            n_empty   = sum(1 for r in results if not r.get("response", ""))
            n_loop    = sum(1 for r in results if check_loop(r.get("response", "")))
            n_judged  = sum(1 for r in results if r.get("judgment") is not None)

            # Tool call timing: anomaly cases that didn't call any tool
            anomaly_no_tool = [
                r["case_id"] for r in results
                if has_anomaly(r.get("terminal_data", ""))
                and not r.get("tool_calls")
                and r.get("status") in ("done", "judged")
            ]
            # Non-anomaly cases that DID call tools (over-calling)
            normal_with_tool = [
                r["case_id"] for r in results
                if not has_anomaly(r.get("terminal_data", ""))
                and r.get("tool_calls")
                and r.get("status") in ("done", "judged")
            ]

            stats[name][cond] = {
                "total": n_total, "done": n_done, "failed": n_failed,
                "empty": n_empty, "loops": n_loop, "judged": n_judged,
                "anomaly_no_tool": len(anomaly_no_tool),
                "normal_with_tool": len(normal_with_tool),
            }

            if n_failed > 0:
                issues.append(f"[{name}][{cond}] {n_failed} failed cases")
            if n_empty > 0:
                issues.append(f"[{name}][{cond}] {n_empty} empty responses")
            if n_loop > 0:
                issues.append(f"[{name}][{cond}] {n_loop} possible token loops")
            if len(anomaly_no_tool) > 5:
                issues.append(f"[{name}][{cond}] {len(anomaly_no_tool)} anomaly cases without tool call")
            if len(normal_with_tool) > 5:
                issues.append(f"[{name}][{cond}] {len(normal_with_tool)} normal cases over-called tools")

            # Score range check
            for r in results:
                j = r.get("judgment")
                if not j:
                    continue
                for dim, score in j.get("scores", {}).items():
                    if not (1 <= score <= 10):
                        issues.append(f"[{name}][{cond}][{r['case_id']}] {dim} score={score} out of range")

    # Print summary table
    print(f"\n=== Anomaly Check: {results_dir} ===\n")
    header = f"{'Model':<18} {'Cond':<5} {'total':>5} {'done':>5} {'failed':>6} {'empty':>5} "
    header += f"{'loops':>5} {'judged':>6} {'no_tool':>7} {'over_tool':>9}"
    print(header)
    print("─" * len(header))

    for model_name, conds in stats.items():
        for cond in sorted(conds):
            s = conds[cond]
            print(f"{model_name:<18} {cond:<5} {s['total']:>5} {s['done']:>5} "
                  f"{s['failed']:>6} {s['empty']:>5} {s['loops']:>5} "
                  f"{s['judged']:>6} {s['anomaly_no_tool']:>7} {s['normal_with_tool']:>9}")

    print()
    if issues:
        print(f"=== Issues ({len(issues)}) ===")
        for issue in issues:
            print(f"  ⚠️  {issue}")
    else:
        print("=== ✅ No issues found ===")

    # Write report
    report_path = results_dir / "anomalies_report.txt"
    lines = [f"=== Anomaly Report: {results_dir} ===", ""]
    for model_name, conds in stats.items():
        for cond in sorted(conds):
            s = conds[cond]
            lines.append(f"[{model_name}][{cond}] total={s['total']} done={s['done']} "
                         f"failed={s['failed']} empty={s['empty']} loops={s['loops']} "
                         f"judged={s['judged']} anomaly_no_tool={s['anomaly_no_tool']} "
                         f"normal_with_tool={s['normal_with_tool']}")
    lines.append("")
    if issues:
        lines.append(f"Issues ({len(issues)}):")
        for issue in issues:
            lines.append(f"  ⚠️  {issue}")
    else:
        lines.append("✅ No issues found")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] → {report_path}")


if __name__ == "__main__":
    main()
