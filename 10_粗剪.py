# -*- coding: utf-8 -*-
"""阶段1 粗剪：全录屏扫描 → AI 剔除非游戏画面 → 产出 粗剪时间线（不改视频文件）
产出：粗剪.json（机器用）+ 粗剪时间线.txt（人看/可编辑）"""
import os, re, json, base64, subprocess, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.chdir(WORK)
MODEL = "glm-5.3-flashx"
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
IV = 10
BATCH = 10

key = open("glm_key.txt", encoding="utf-8").read().strip().splitlines()[-1].strip()

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        print(r.stderr[-600:]); raise SystemExit("[失败] " + " ".join(cmd[:4]))

def probe(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", f], capture_output=True, text=True)
    return float(r.stdout.strip())

def ask_llm(content):
    import time
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}],
                       "temperature": 0.5}).encode("utf-8")
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(API, data=body, headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"    [重试 {attempt}/3] {str(e)[:50]}")
            time.sleep(3 * attempt)
    raise Exception("API 连续3次失败")

# 已有粗剪结果则直接复用（要重扫就删掉 粗剪.json）
if os.path.exists("粗剪.json"):
    print("[跳过] 粗剪.json 已存在（要重新扫描请删除该文件）")
    sys.exit(0)

dur = probe("game.mp4")
n_frames = int(dur // IV)
print(f"[粗剪] 录屏 {dur/60:.1f} 分钟，每 {IV}s 抽 1 帧，共 {n_frames} 帧")

os.makedirs("_scan", exist_ok=True)
for i in range(n_frames):
    f = f"_scan/{i:04d}.jpg"
    if not os.path.exists(f):
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(i * IV), "-i", "game.mp4",
             "-frames:v", "1", "-q:v", "6", "-vf", "scale=512:-2", f])
print("[粗剪] 抽帧完成")

CLASS_PROMPT = ("你是游戏视频剪辑助手。下面是同一段录屏按时间顺序（每10秒一帧）的截图。"
    "对每一帧输出：type（游戏/桌面/加载/登录/其他）、desc（画面内容一句话，游戏画面要说清在干什么）、"
    "score（1-10 游戏精彩度：战斗/抓宠/稀有事件/进度突破高分，菜单/走路/挂机/加载低分，非游戏帧0分）。"
    "只输出 JSON 数组：[{\"i\":帧序号,\"type\":\"...\",\"desc\":\"...\",\"score\":数字},...]，不要其他文字。")

frames = []
for start in range(0, n_frames, BATCH):
    idxs = list(range(start, min(start + BATCH, n_frames)))
    content = [{"type": "text",
                "text": CLASS_PROMPT + f" 帧序号 {idxs[0]} 到 {idxs[-1]}，共{len(idxs)}张图，按顺序对应。"}]
    for i in idxs:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," +
                                      base64.b64encode(open(f"_scan/{i:04d}.jpg", "rb").read()).decode()}})
    try:
        raw = re.sub(r"^```(json)?|```$", "", ask_llm(content).strip(), flags=re.M).strip()
        frames.extend(json.loads(raw[raw.index("["):raw.rindex("]") + 1]))
        print(f"  已分析 {len(frames)}/{n_frames} 帧")
    except Exception as e:
        print(f"  批次 {start} 失败跳过: {e}")

if not frames:
    raise SystemExit("[!] 没有分析成功的帧")

json.dump({"dur": dur, "iv": IV, "frames": frames},
          open("粗剪.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 人读版时间线
game_cnt = sum(1 for f in frames if f.get("type") == "游戏")
lines = [f"录屏总长 {dur/60:.1f} 分钟 | 游戏画面帧 {game_cnt}/{len(frames)} | 删除非游戏内容后剩约 {game_cnt*IV/60:.1f} 分钟", ""]
for f in sorted(frames, key=lambda x: x["i"]):
    t = f["i"] * IV
    mark = {"游戏": "▶", "桌面": "✂", "加载": "✂", "登录": "✂"}.get(f.get("type", "其他"), "✂")
    lines.append(f"{mark} {int(t//60):02d}:{int(t%60):02d}  [{f.get('type','?')}|{f.get('score',0)}分] {f.get('desc','')}")
open("粗剪时间线.txt", "w", encoding="utf-8").write("\n".join(lines))
print(f"[粗剪完成] 游戏画面 {game_cnt*IV/60:.1f} 分钟 / 全片 {dur/60:.1f} 分钟 → 粗剪时间线.txt")
