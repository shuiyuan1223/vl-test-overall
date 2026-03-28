"""Extract BCD scores from agent JSONL files."""
import json, sys
from pathlib import Path

ABLATION_DIMS = {
    "B": ["视觉识别准确率", "数据引用质量", "图像与上下文一致性"],
    "C": ["数值读取精度", "数据引用质量", "任务完成度"],
    "D": ["数据引用质量", "任务完成度"],
}

def extract_from_jsonl(jsonl_path: str, model_name: str, output_path: str):
    best_write = None
    best_len = 0

    with open(jsonl_path, 'rb') as f:
        for line in f:
            try:
                d = json.loads(line.decode('utf-8', errors='replace'))
                msg = d.get('message', {})
                for c in msg.get('content', []):
                    if c.get('type') == 'tool_use' and c.get('name') == 'Write':
                        inp = c.get('input', {})
                        content = inp.get('content', '')
                        if len(content) > best_len and (model_name.replace('.','') in inp.get('file_path','') or 'BCD' in inp.get('file_path','')):
                            best_len = len(content)
                            best_write = content
            except:
                pass

    if not best_write:
        print(f"No Write call found for {model_name}")
        return False

    print(f"Found Write call: {len(best_write)} chars")

    # Try parse
    try:
        data = json.loads(best_write)
    except:
        try:
            data = json.loads(best_write.encode('latin-1').decode('utf-8'))
        except Exception as e:
            print(f"Parse error: {e}")
            return False

    # Detect format and rebuild
    out = {model_name: {}}

    # Format 1: {model: {B: {rowXXX: {...}}, C: {...}, D: {...}}}
    if model_name in data:
        out = data
        print(f"Direct format: {model_name}")
    # Format 2: {B: {rowXXX: {...}}, C: {...}, D: {...}}
    elif 'B' in data or 'C' in data or 'D' in data:
        out = {model_name: data}
        print("Condition-keyed format")
    # Format 3: [{condition: 'B', cases: [...]}]
    elif isinstance(data, list):
        for cond_data in data:
            cond = cond_data.get('condition', '')
            cases = cond_data.get('cases', [])
            if cond and cases:
                out[model_name][cond] = {}
                dims = ABLATION_DIMS.get(cond, [])
                for case in cases:
                    cid = case.get('case_id', case.get('id', ''))
                    scores = case.get('scores', {})
                    case_out = {}
                    score_vals = list(scores.values())
                    for i, dim in enumerate(dims):
                        if i < len(score_vals):
                            case_out[dim] = str(score_vals[i])
                    case_out['overall_comment'] = case.get('overall_comment', case.get('note', ''))[:200]
                    out[model_name][cond][cid] = case_out
        print(f"List format: {list(out[model_name].keys())}")
    else:
        # Format 4: cases array with condition field
        cases_key = next((k for k in data if 'case' in k.lower()), None)
        if cases_key:
            print(f"Cases key: {cases_key}")
            for case in data[cases_key]:
                cond = case.get('condition', 'A')
                cid = case.get('case_id', '')
                scores = case.get('scores', {})
                if cond not in out[model_name]:
                    out[model_name][cond] = {}
                dims = ABLATION_DIMS.get(cond, [])
                case_out = {}
                score_vals = list(scores.values())
                for i, dim in enumerate(dims):
                    if i < len(score_vals):
                        case_out[dim] = str(score_vals[i])
                case_out['overall_comment'] = case.get('overall_comment', '')[:200]
                out[model_name][cond][cid] = case_out

    # Count
    for cond in ['B', 'C', 'D']:
        n = len(out.get(model_name, {}).get(cond, {}))
        print(f"  {cond}: {n} cases")

    Path(output_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), 'utf-8')
    print(f"Written to {output_path}")
    return True


BASE = "C:/Users/Administrator/.claude/projects/D--pha-v2/a006acb3-6e3e-470c-aac9-4b9cfd6adab3/subagents"

extract_from_jsonl(
    f"{BASE}/agent-abffb04ba01d2bdfa.jsonl",
    "Qwen3.5-397B",
    "D:/pha-v2/tests/vl-onapp-eval/scores_397B_BCD.json"
)

print("\n---\n")

extract_from_jsonl(
    f"{BASE}/agent-a29dce8494892993f.jsonl",
    "Qwen3.5-122B",
    "D:/pha-v2/tests/vl-onapp-eval/scores_122B_BCD.json"
)
