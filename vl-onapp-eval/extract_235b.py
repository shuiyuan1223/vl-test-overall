import json, sys

f = r"C:/Users/Administrator/.claude/projects/D--pha-v2/a006acb3-6e3e-470c-aac9-4b9cfd6adab3/subagents/agent-af11ec1c6a36a5120.jsonl"
best = ""
best_len = 0
with open(f, encoding='utf-8', errors='replace') as fh:
    for line in fh:
        try:
            d = json.loads(line)
            msg = d.get('message', {})
            if msg.get('role') == 'assistant':
                for c in msg.get('content', []):
                    if c.get('type') == 'text':
                        txt = c.get('text', '')
                        if '"Qwen3-235B"' in txt and 'row002' in txt:
                            if len(txt) > best_len:
                                best_len = len(txt)
                                best = txt
        except:
            pass

if best:
    start = best.rfind('{', 0, best.find('"Qwen3-235B"'))
    print(f"Found block length={len(best)}, json_start={start}")
    print(best[start:start+3000])
else:
    print("NOT FOUND - searching for any row002...")
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                d = json.loads(line)
                msg = d.get('message', {})
                for c in msg.get('content', []):
                    if c.get('type') == 'text' and 'row002' in c.get('text',''):
                        print(c['text'][:500])
                        print('---')
            except:
                pass
