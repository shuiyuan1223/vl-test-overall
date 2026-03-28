"""Convert agent-generated score JSON to batch_score.py import format."""
import json, sys
from pathlib import Path

KIMI_DIM_MAP = {
    "d1_visual_recognition": "视觉识别准确率",
    "d2_hallucination_control": "幻觉控制率",
    "d3_numeric_accuracy": "数值读取精度",
    "d4_output_timing": "输出时序合规",
    "d5_safety_disclaimer": "安全声明合规",
    "d6_boundary_restraint": "边界克制合规",
    "d7_data_citation": "数据引用质量",
    "d8_terminal_data_priority": "端侧数据优先性",
    "d9_tool_call_timing": "工具调用时机准确性",
    "d10_tool_result_integration": "工具调用结果整合度",
    "d11_task_completion": "任务完成度",
    "d12_image_context_consistency": "图像与上下文一致性",
}

def convert(input_path: str, output_path: str):
    data = json.loads(Path(input_path).read_text("utf-8"))
    
    # Detect format
    model = data.get("model", "")
    condition = data.get("condition", "A")
    
    # Get cases list
    cases = data.get("scores") or data.get("cases") or []
    
    out = {model: {condition: {}}}
    
    for case in cases:
        case_id = case.get("case_id") or case.get("id")
        scores = case.get("scores", {})
        notes = case.get("notes") or case.get("overall_note") or case.get("summary") or ""
        
        case_out = {}
        for k, v in scores.items():
            # Map english dim names to Chinese
            zh_key = KIMI_DIM_MAP.get(k, k)
            # Convert int scores to "N" string format (batch_score.py parse_score_entry handles this)
            case_out[zh_key] = str(v)
        
        case_out["overall_comment"] = notes
        out[model][condition][case_id] = case_out
    
    Path(output_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(f"Converted {len(cases)} cases → {output_path}")

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
