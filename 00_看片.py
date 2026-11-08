# -*- coding: utf-8 -*-
"""00 看片写稿：读取 highlights.txt 的精华段 → 每段抽3帧 → GLM-4V 看图写解说 → 解说稿.txt
需要 workflow\glm_key.txt 里放智谱 API key（glm-4v-flash 免费）"""
import os, re, base64, json, subprocess, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.chdir(WORK)
MODEL = "glm-5.3-flashx"  # 视觉+文案更强，消耗资源包 token（免费包有 2000 万+）
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

key_path = os.path.join(WORK, "glm_key.txt")
key = open(key_path, encoding="utf-8").read().strip() if os.path.exists(key_path) else os.environ.get("GLM_API_KEY", "")
if not key:
    raise SystemExit("[!] 缺少 glm_key.txt（里面只放智谱 API key）")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        print(r.stderr[-800:]); raise SystemExit("[失败] " + " ".join(cmd[:4]))

def parse_t(t):
    t = t.strip()
    if ":" in t:
        parts = [float(x) for x in t.split(":")]
        return sum(x * 60**i for i, x in enumerate(reversed(parts)))
    return float(t)

# ---------- 精华段 ----------
hl = [l.strip() for l in open("highlights.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
segs = []
for l in hl:
    if "-" in l:
        a, b = l.split("-", 1); segs.append((parse_t(a), parse_t(b)))
    else:
        a = parse_t(l); segs.append((a, a + 30.0))
if not segs:
    raise SystemExit("[!] highlights.txt 没有时间段")
print(f"[看片] {len(segs)} 段，每段抽3帧给 GLM-4V 分析")

# ---------- 抽帧 ----------
frames = []
for i, (a, b) in enumerate(segs):
    d = b - a
    fs = []
    for j, ratio in enumerate((0.15, 0.5, 0.85)):
        f = f"_look{i}_{j}.jpg"
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(a + d * ratio), "-i", "game.mp4",
             "-frames:v", "1", "-q:v", "4", f])
        fs.append(f)
    frames.append(fs)

# ---------- 逐段问 GLM-4V ----------
SYS = ("你是B站游戏怀旧解说博主，语气口语化、有梗、能勾回忆，擅长从画面细节展开。"
       "根据我给的几帧游戏画面，写这一段的解说词。要求："
       "1) 只根据画面里真实出现的内容描述，不要编造画面外的东西；"
       "2) 90-130字（约对应25秒配音）；"
       "3) 直接输出解说词正文，不要任何标题、序号、引号。")

def ask(images_b64, seg_hint, user_note):
    content = [{"type": "text",
                "text": f"这是同一段游戏录像里的3帧画面（按时间顺序）。这段时长约{seg_hint}秒。{user_note}\n请写这段的解说词。"}]
    for b in images_b64:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + b}})
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": SYS}, {"role": "user", "content": content}],
        "temperature": 0.8}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()

note = ""
if os.path.exists("看片备注.txt"):
    note = open("看片备注.txt", encoding="utf-8").read().strip()

paras = []
for i, fs in enumerate(frames):
    b64s = [base64.b64encode(open(f, "rb").read()).decode() for f in fs]
    hint = f"{segs[i][1] - segs[i][0]:.0f}"
    txt = ask(b64s, hint, note)
    paras.append(re.sub(r"\s+", " ", txt))
    print(f"  段{i} 解说词: {txt[:30]}...")

# ---------- 写解说稿 ----------
out = "\n\n".join(paras) + "\n"
old = open("解说稿.txt", encoding="utf-8").read() if os.path.exists("解说稿.txt") else ""
tail = old.split("—————", 1)[1] if "—————" in old else ""
if tail:
    out += "\n—————" + tail
open("解说稿.txt", "w", encoding="utf-8").write(out)
for fs in frames:
    for f in fs:
        os.remove(f)
print(f"[OK] 解说稿.txt 已按 {len(paras)} 段画面自动生成（记得过目改一遍再配音）")
