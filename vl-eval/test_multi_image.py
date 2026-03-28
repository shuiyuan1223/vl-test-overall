import base64, requests, json, uuid, os, sys

PORT = 8000
NO_PROXY = {"http": None, "https": None}

img_dir = r"D:\pha-v2\tests\test-img"
imgs = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:2]
print(f"Using images: {imgs}")

image_ids = []
for fname in imgs:
    fpath = os.path.join(img_dir, fname)
    with open(fpath, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = 'image/png' if fname.lower().endswith('.png') else 'image/jpeg'
    r = requests.post(f"http://127.0.0.1:{PORT}/api/upload/diet-photo",
                      json={"imageBase64": b64, "mimeType": mime},
                      proxies=NO_PROXY, timeout=15)
    data = r.json()
    short = fname[:40]
    print(f"  uploaded '{short}' -> imageId={data.get('imageId','ERROR')}")
    if data.get('imageId'):
        image_ids.append(data['imageId'])

assert len(image_ids) == 2, f"Expected 2 image IDs, got {len(image_ids)}"
print(f"\nOK Both images uploaded: {image_ids}")

content = f"[vision] image_ids={','.join(image_ids)} 这是两张图片，帮我简单描述一下分别看到了什么"
payload = {
    "messages": [{"role": "user", "content": content}],
    "thread_id": str(uuid.uuid4()),
    "run_id": str(uuid.uuid4()),
    "context": [],
}

print(f"\nSending multi-image chat request...")
collected = []
with requests.post(f"http://127.0.0.1:{PORT}/api/ag-ui",
                   json=payload,
                   headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
                   proxies=NO_PROXY, stream=True, timeout=120) as resp:
    for raw in resp.iter_lines():
        line = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
        if not line or not line.startswith("data:"):
            continue
        ds = line[5:].strip()
        if ds == "[DONE]":
            break
        try:
            evt = json.loads(ds)
            t = evt.get("type", "")
            if t == "TextMessageContent":
                collected.append(evt.get("delta", ""))
            elif t in ("RunFinished", "RunError"):
                break
        except Exception:
            pass

result = "".join(collected).strip()
print(f"\n=== Response ===")
sys.stdout.buffer.write(result[:800].encode('utf-8'))
print()

if result and not result.startswith("⚠️"):
    print("\nPASS: multi-image response received successfully")
else:
    print(f"\nFAIL: unexpected response: {result[:100]}")
    sys.exit(1)
