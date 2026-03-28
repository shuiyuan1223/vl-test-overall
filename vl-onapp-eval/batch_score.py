"""
batch_score.py — Claude Code 人工评分工具

用法:
  python batch_score.py                         # 交互模式：逐条展示，等待评分输入
  python batch_score.py --export                # 导出待评分的 scoring_sheet.txt（供 Claude Code 批量阅读）
  python batch_score.py --import scores.json   # 导入 Claude Code 输出的评分 JSON 写回结果
  python batch_score.py --review               # 查看评分进度
  python batch_score.py --model Qwen3.5-397B   # 只处理指定模型
  python batch_score.py --condition A          # 只处理指定条件

评分格式（--import 时输入的 scores.json）:
{
  "Qwen3.5-397B": {
    "A": {
      "row002": {
        "视觉识别准确率": "8 睡眠阶段颜色正确",
        "幻觉控制率": "9",
        "数值读取精度": "6 HRV读42但虚构了周均值",
        ...
        "overall_comment": "能正确读取terminal_data，HRV偏低未主动查询云侧"
      }
    }
  }
}

注意：评分格式为 "分数 扣分原因" 或纯 "分数"（满分无需说明）
"""

import os, sys, json, argparse
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EVAL_DIR  = Path(__file__).parent
RESULTS_BASE = EVAL_DIR / "results"

DIMS = [
    "视觉识别准确率", "幻觉控制率", "数值读取精度", "输出时序合规",
    "安全声明合规",   "边界克制合规", "数据引用质量", "端侧数据优先性",
    "工具调用时机准确性", "工具调用结果整合度", "任务完成度", "图像与上下文一致性",
]

# 消融评分时，各条件只需评分的核心维度
ABLATION_DIMS = {
    "A": DIMS,  # 全量
    "B": ["视觉识别准确率", "数据引用质量", "图像与上下文一致性"],       # description 影响
    "C": ["数值读取精度", "数据引用质量", "任务完成度"],                    # knowledge 影响
    "D": ["数据引用质量", "任务完成度"],                                    # 联合效果
}


def find_latest_results_dir() -> Path | None:
    runs = sorted(RESULTS_BASE.glob("run_*"), reverse=True)
    return runs[0] if runs else None


def load_all_results(results_dir: Path, model_filter=None, cond_filter=None) -> dict:
    """Returns {model_name: {condition: [results]}}"""
    out = {}
    for json_path in sorted(results_dir.glob("*_results.json")):
        data = json.loads(json_path.read_text("utf-8"))
        name = data["model"]["name"]
        if model_filter and name != model_filter:
            continue
        out[name] = {}
        for cond, results in data.get("conditions", {}).items():
            if cond_filter and cond != cond_filter:
                continue
            out[name][cond] = results
    return out


def parse_score_entry(raw: str) -> tuple[int, str]:
    """Parse '8 扣分原因' → (8, '扣分原因') or '9' → (9, '')"""
    raw = raw.strip()
    if not raw:
        return 0, "未评分"
    parts = raw.split(" ", 1)
    try:
        score = int(parts[0])
        note  = parts[1].strip() if len(parts) > 1 else ""
        return max(1, min(10, score)), note
    except ValueError:
        return 0, raw


def export_scoring_sheet(results_dir: Path, model_filter=None, cond_filter=None):
    """Export a formatted text file for Claude Code to read and score."""
    all_results = load_all_results(results_dir, model_filter, cond_filter)
    output_path = results_dir / "scoring_sheet.txt"

    lines = []
    lines.append("=" * 80)
    lines.append("PHA OnApp VL 评测 — 评分表")
    lines.append(f"目录: {results_dir}")
    lines.append("=" * 80)
    lines.append("")
    lines.append("评分格式: 「分数 扣分原因」或 「分数」(满分无需说明)")
    lines.append("示例: 视觉识别准确率: 7 未识别深睡偏高标记")
    lines.append("")

    total_to_score = 0
    already_scored = 0

    for model_name, conditions in all_results.items():
        for condition, results in sorted(conditions.items()):
            dims_to_score = ABLATION_DIMS.get(condition, DIMS)

            for result in results:
                if result.get("judgment") is not None:
                    already_scored += 1
                    continue

                status = result.get("status", "")
                if status in ("failed",):
                    continue  # skip failed cases

                total_to_score += 1
                case_id = result["case_id"]

                # Terminal data summary (key anomalies only)
                td_raw = result.get("terminal_data", "")
                try:
                    td = json.loads(td_raw)
                    pages = td.get("pages", {})
                    # Extract anomaly signals
                    anomalies = []
                    td_str = json.dumps(td, ensure_ascii=False)
                    for kw in ["偏低", "偏高", "异常", "高于正常", "低于正常"]:
                        if kw in td_str:
                            anomalies.append(kw)
                    td_summary = f"currentPage={td.get('currentPage','?')} | 异常标签={anomalies or '无'}"
                    td_summary += f"\n  pages keys: {list(pages.keys())}"
                except Exception:
                    td_summary = td_raw[:200]

                # Tool calls summary
                tool_calls = result.get("tool_calls", [])
                tools_str = ", ".join(t.get("name", "?") for t in tool_calls) if tool_calls else "无"

                # Cloud data summary
                cloud = result.get("cloud_data", "")
                cloud_summary = cloud[:150] + "..." if len(cloud) > 150 else cloud

                lines.append(f"{'─'*70}")
                lines.append(f"【{model_name}】[条件{condition}] {case_id} | {result['image_name']}")
                lines.append(f"问题: {result['query']}")
                lines.append(f"页面数据摘要: {td_summary}")
                lines.append(f"工具调用: {tools_str}")
                if result.get("injected", {}).get("description"):
                    lines.append(f"注入描述: [已注入 {len(result['injected']['description'])}字]")
                if result.get("injected", {}).get("knowledge"):
                    lines.append(f"注入知识: [已注入 {len(result['injected']['knowledge'])}字]")
                lines.append(f"云侧参考(1.0): {cloud_summary}")
                lines.append("")
                lines.append("─── 模型回复 ───")
                resp = result.get("response", "")
                if result.get("status") == "token_loop":
                    lines.append(f"⚠️ TOKEN LOOP ({len(resp)}字) 前500字: {resp[:500]}")
                else:
                    lines.append(resp[:1500] + ("...[截断]" if len(resp) > 1500 else ""))
                lines.append("")
                lines.append("─── 评分（以下各维度填写）───")
                for dim in dims_to_score:
                    lines.append(f"{dim}: ")
                lines.append("overall_comment: ")
                lines.append("")

    lines.append(f"\n=== 统计: 待评分 {total_to_score} 条, 已评分 {already_scored} 条 ===")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[export] 评分表已导出 → {output_path}")
    print(f"[export] 待评分: {total_to_score} 条 | 已评分: {already_scored} 条")
    print(f"[export] 阅读文件，按格式填写评分后 python batch_score.py --import <json_path>")


def import_scores(scores_json_path: Path, results_dir: Path):
    """Read Claude Code's scored JSON and write back into result files."""
    scores_data = json.loads(scores_json_path.read_text("utf-8"))

    # Load all result files
    result_files = {}
    for json_path in results_dir.glob("*_results.json"):
        data = json.loads(json_path.read_text("utf-8"))
        result_files[data["model"]["name"]] = (json_path, data)

    total_written = 0

    for model_name, conditions in scores_data.items():
        if model_name not in result_files:
            print(f"[import] ⚠️  Model not found: {model_name}")
            continue

        json_path, data = result_files[model_name]

        for condition, case_scores in conditions.items():
            if condition not in data.get("conditions", {}):
                continue

            for result in data["conditions"][condition]:
                case_id = result["case_id"]
                if case_id not in case_scores:
                    continue

                raw_scores = case_scores[case_id]
                dims_to_score = ABLATION_DIMS.get(condition, DIMS)

                scores_parsed = {}
                reasons_parsed = {}
                overall = ""

                for dim in dims_to_score:
                    if dim in raw_scores:
                        score, note = parse_score_entry(str(raw_scores[dim]))
                        scores_parsed[dim] = score
                        reasons_parsed[dim] = note or "Claude Code人工评分"
                    else:
                        scores_parsed[dim] = 0
                        reasons_parsed[dim] = "未评分"

                if "overall_comment" in raw_scores:
                    overall = raw_scores["overall_comment"]

                result["judgment"] = {
                    "scores":  scores_parsed,
                    "reasons": reasons_parsed,
                    "overall_comment": overall,
                    "judge": "claude-code-manual",
                    "judge_dims": dims_to_score,
                }
                result["status"] = "judged"
                total_written += 1

        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        print(f"[import] {model_name} → {json_path}")

    print(f"[import] ✓ {total_written} 条评分写入完成")


def show_review(results_dir: Path, model_filter=None):
    """Show scoring progress."""
    print(f"\n=== 评分进度: {results_dir} ===\n")
    for json_path in sorted(results_dir.glob("*_results.json")):
        data = json.loads(json_path.read_text("utf-8"))
        name = data["model"]["name"]
        if model_filter and name != model_filter:
            continue
        print(f"  {name}:")
        for cond, results in sorted(data.get("conditions", {}).items()):
            total   = len(results)
            done    = sum(1 for r in results if r.get("status") == "done")
            judged  = sum(1 for r in results if r.get("judgment") is not None)
            failed  = sum(1 for r in results if r.get("status") == "failed")
            loops   = sum(1 for r in results if r.get("status") == "token_loop")
            print(f"    [{cond}] 总={total} 已跑={done} 已评={judged} "
                  f"失败={failed} loop={loops} 待评={done-judged}")
    print()


def compute_summary(results_dir: Path):
    """Compute and print score summary."""
    print(f"\n=== 评分汇总 ===\n")
    for json_path in sorted(results_dir.glob("*_results.json")):
        data = json.loads(json_path.read_text("utf-8"))
        name = data["model"]["name"]
        print(f"  {name}:")
        for cond, results in sorted(data.get("conditions", {}).items()):
            judged = [r for r in results if r.get("judgment")]
            if not judged:
                continue
            dim_scores: dict[str, list] = {}
            for r in judged:
                for dim, score in r["judgment"].get("scores", {}).items():
                    if score > 0:
                        dim_scores.setdefault(dim, []).append(score)
            overall_scores = []
            for scores_list in dim_scores.values():
                overall_scores.extend(scores_list)
            overall_avg = sum(overall_scores) / len(overall_scores) if overall_scores else 0
            print(f"    [{cond}] 综合均分={overall_avg:.2f} (n={len(judged)})")
            for dim, scores_list in dim_scores.items():
                avg = sum(scores_list) / len(scores_list)
                print(f"      {dim}: {avg:.2f}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export",  action="store_true", help="导出评分表 scoring_sheet.txt")
    parser.add_argument("--import",  dest="import_path", help="导入评分 JSON 路径")
    parser.add_argument("--review",  action="store_true", help="查看评分进度")
    parser.add_argument("--summary", action="store_true", help="计算并打印分数汇总")
    parser.add_argument("--model",   help="只处理指定模型")
    parser.add_argument("--condition", help="只处理指定条件 (A/B/C/D)")
    parser.add_argument("--run",     help="指定 run 目录名 (如 run_20260320_1000)")
    args = parser.parse_args()

    # Resolve results dir
    if args.run:
        results_dir = RESULTS_BASE / args.run
    else:
        results_dir = find_latest_results_dir()
    if not results_dir or not results_dir.exists():
        print(f"[error] No results dir found. Run run_onapp_eval.py first.")
        return

    if args.export:
        export_scoring_sheet(results_dir, args.model, args.condition)
    elif args.import_path:
        import_scores(Path(args.import_path), results_dir)
    elif args.review:
        show_review(results_dir, args.model)
    elif args.summary:
        compute_summary(results_dir)
    else:
        # Default: show review
        show_review(results_dir, args.model)
        print("使用 --export 导出评分表，--import <json> 导入评分")


if __name__ == "__main__":
    main()
