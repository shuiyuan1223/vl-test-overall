import json, os

RESULT_DIR = 'results/run_20260319_1205'
MODELS = ['Qwen3.5-397B', 'Qwen3.5-122B', 'kimi-k2.5', 'Qwen3VL-235B', 'GLM-4.6V', 'MiniMax-01']
DIMS = ['视觉识别准确率','幻觉控制率','数值读取精度','输出时序合规','安全声明合规','边界克制合规','数据引用质量','工具调用合理性','任务完成度','图像与上下文一致性','主动澄清行为']

issues = []

for model in MODELS:
    fpath = f'{RESULT_DIR}/{model}_results.json'
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get('results', [])
    if len(results) != 16:
        issues.append(f'[WRONG_COUNT] {model}: expected 16 cases, got {len(results)}')

    for i, r in enumerate(results):
        label = r.get('label', f'case_{i}')
        resp = r.get('response', '')
        status = r.get('status', '')
        judgment = r.get('judgment', {})
        scores = judgment.get('scores', {}) if judgment else {}
        comment = judgment.get('comment', '') if judgment else ''

        # Empty response
        if not resp or resp.strip() == '':
            issues.append(f'[EMPTY_RESPONSE] {model}/{label}')

        # Empty judgment
        if not judgment:
            issues.append(f'[EMPTY_JUDGMENT] {model}/{label}')
        elif not scores:
            issues.append(f'[EMPTY_SCORES] {model}/{label}')
        else:
            # Bug fix 3a: use correct field name overall_comment, not comment
            overall_comment = judgment.get('overall_comment', '')
            if not overall_comment:
                issues.append(f'[EMPTY_OVERALL_COMMENT] {model}/{label}')

        # Missing dimensions in scores
        if scores:
            missing = [d for d in DIMS if d not in scores]
            if missing:
                issues.append(f'[MISSING_DIMS] {model}/{label}: {missing}')

            # Out of range scores
            oob = {k: v for k, v in scores.items() if not (1 <= v <= 10)}
            if oob:
                issues.append(f'[SCORE_OOB] {model}/{label}: {oob}')

        # Bug fix 3b: only flag actual PHA system errors (⚠️ at start of response), not markdown emoji
        if resp and resp.strip().startswith('\u26a0\ufe0f'):
            if '404' not in resp:
                issues.append(f'[OTHER_ERROR] {model}/{label}: {resp[:120]}')

        # Bug fix 3b: judged is a valid status set by write_scores.py, allow it
        if status not in ('success', 'error', 'judged', ''):
            issues.append(f'[WEIRD_STATUS] {model}/{label}: status={status}')

        # error status but scored high
        if status == 'error' and scores and any(v > 2 for v in scores.values()):
            issues.append(f'[ERROR_WITH_GOOD_SCORE] {model}/{label}: status=error but scores>2')

        # Missing tool_calls field
        if 'tool_calls' not in r:
            issues.append(f'[NO_TOOL_CALLS_FIELD] {model}/{label}')

        # Suspiciously short response (ignore 404 errors)
        if resp and '404' not in resp and len(resp.strip()) < 20:
            issues.append(f'[SHORT_RESPONSE] {model}/{label}: len={len(resp.strip())} text={repr(resp.strip()[:60])}')

        # Token loop detection: response > 5000 chars
        if resp and len(resp) > 5000:
            issues.append(f'[VERY_LONG_RESPONSE] {model}/{label}: len={len(resp)} (possible token loop)')

        # Check for repeated substrings (token loop heuristic)
        if resp and len(resp) > 500:
            chunk = resp[:100]
            if resp.count(chunk) > 5:
                issues.append(f'[REPETITION_LOOP] {model}/{label}: first 100 chars repeated {resp.count(chunk)}x')

out_path = 'anomalies_report.txt'
with open(out_path, 'w', encoding='utf-8') as out:
    if issues:
        for iss in issues:
            out.write(iss + '\n')
    else:
        out.write('No issues found\n')
    out.write(f'\nTotal issues: {len(issues)}\n')
print(f'Written to {out_path}')
