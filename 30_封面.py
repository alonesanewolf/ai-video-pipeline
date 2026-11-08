# -*- coding: utf-8 -*-
"""30 封面：最高分画面 + GLM 悬念标题 → cover.jpg（B站封面）"""
import os, re, json, sys, subprocess, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def probe_best_t():
    data = json.load(open("粗剪.json", encoding="utf-8"))
    best = max(data["frames"], key=lambda f: f.get("score", 0))
    return best["i"] * data["iv"]

def ask(content):
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    key = open("glm_key.txt", encoding="utf-8").read().strip().splitlines()[-1].strip()
    body = json.dumps({"model": "glm-5.3-flashx", "messages": [{"role": "user", "content":
                       content}], "temperature": 0.8}).encode("utf-8")
    req = urllib.request.Request("https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()

if not os.path.exists("game.mp4"):
    raise SystemExit("[!] 没有 game.mp4")
t = probe_best_t()
gist = open("解说稿.txt", encoding="utf-8").read().split("—————")[0][:400]
# 抽最高分帧 → 16:9 裁切（按宽度裁，源是16:10）
subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", "game.mp4",
                "-frames:v", "1", "-vf", "crop=iw:iw*9/16:0:(ih-iw*9/16)/2,scale=1680:944",
                "-q:v", "2", "_cover_base.jpg"], check=True)
# 标题必须看着封面图写（图文一致），解说稿只做背景参考
import base64
img_b64 = base64.b64encode(open("_cover_base.jpg", "rb").read()).decode()
title = ask([{"type": "text", "text":
    ("第一张图是这条怀旧游戏解说视频的封面底图，视频整体讲的是：" + gist +
     "。请给封面写大标题：10字以内、悬念或反差式，标题必须描述底图画面里的内容（不是泛泛的情怀口号）。"
     "只输出标题文字本身。")},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}}]).splitlines()[0].strip()
title = re.sub(r'[\\/:*?"<>|]', "", title)[:12]
print(f"[封面] 标题: {title}")
open("_ct.txt", "w", encoding="utf-8").write(title)
r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "_cover_base.jpg",
    "-vf", ("drawtext=fontfile='C\\:/Windows/Fonts/msyhbd.ttc':textfile=_ct.txt:"
            "fontsize=110:fontcolor=white:borderw=7:bordercolor=black@0.9:shadowy=5:"
            "x=(w-text_w)/2:y=h-text_h-60"),
    "-q:v", "2", "cover.jpg"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
for f in ("_cover_base.jpg", "_ct.txt"):
    if os.path.exists(f):
        os.remove(f)
if r.returncode != 0:
    print(r.stderr[-400:])
    raise SystemExit("[!] 封面文字烧录失败（字体路径问题），基础图已保留为 cover_base")
print("[OK] cover.jpg 已生成（最高分画面+大字标题）")
