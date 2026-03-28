"""Extract 235B scores from agent JSONL, fix encoding, write correct file."""
import json, re
from pathlib import Path

JSONL = r"C:/Users/Administrator/.claude/projects/D--pha-v2/a006acb3-6e3e-470c-aac9-4b9cfd6adab3/subagents/agent-af11ec1c6a36a5120.jsonl"

DIMS = [
    "视觉识别准确率", "幻觉控制率", "数值读取精度", "输出时序合规",
    "安全声明合规", "边界克制合规", "数据引用质量", "端侧数据优先性",
    "工具调用时机准确性", "工具调用结果整合度", "任务完成度", "图像与上下文一致性",
]

# Extract raw bytes of Write call content
write_content_bytes = None
with open(JSONL, 'rb') as f:
    for line in f:
        try:
            d = json.loads(line.decode('utf-8', errors='replace'))
            msg = d.get('message', {})
            for c in msg.get('content', []):
                if c.get('type') == 'tool_use' and c.get('name') == 'Write':
                    inp = c.get('input', {})
                    if 'scores_235B' in inp.get('file_path', ''):
                        # Get the raw content
                        content_str = inp.get('content', '')
                        write_content_bytes = content_str
                        print(f"Found Write call with {len(content_str)} chars")
        except:
            pass

if not write_content_bytes:
    print("No Write call found")
    exit(1)

# Try to parse the JSON (may have encoding issues in keys)
try:
    data = json.loads(write_content_bytes)
    print(f"Parsed JSON: {len(data.get('cases', []))} cases")
except Exception as e:
    print(f"Parse error: {e}")
    # Try fixing the encoding first
    # The content might be double-encoded
    try:
        fixed = write_content_bytes.encode('latin-1').decode('utf-8')
        data = json.loads(fixed)
        print(f"Fixed with latin-1->utf-8: {len(data.get('cases', []))} cases")
    except:
        print("Cannot parse, extracting scores numerically...")
        data = None

if data:
    cases = data.get('cases', [])
    # Rebuild with correct dim names
    out = {"Qwen3-235B": {"A": {}}}

    for case in cases:
        cid = case.get('case_id', '')
        scores = case.get('scores', {})
        note = case.get('overall_comment', '')

        # Map scores by position (since dim names may be garbled)
        score_vals = list(scores.values())

        case_out = {}
        for i, dim in enumerate(DIMS):
            if i < len(score_vals):
                v = score_vals[i]
                case_out[dim] = str(v)

        case_out['overall_comment'] = note[:200] if note else ''
        out["Qwen3-235B"]["A"][cid] = case_out

    out_path = Path(r"D:/pha-v2/tests/vl-onapp-eval/scores_235B_A.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), 'utf-8')
    print(f"Written {len(out['Qwen3-235B']['A'])} cases to {out_path}")
else:
    print("Could not recover scores")
