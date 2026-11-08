# -*- coding: utf-8 -*-
"""阶段2 细剪：读粗剪结果 → AI 决定叙事结构（挑段/排序/配比）→ 产出剪辑决策 + 逐段文案
产出：highlights.txt + 解说稿.txt（供 01_配音 / 03_剪辑 消费）"""
import os, re, json, base64, subprocess, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.chdir(WORK)
MODEL = "glm-5.3-flashx"
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

key = open("glm_key.txt", encoding="utf-8").read().strip().splitlines()[-1].strip()

def ask_llm(content, temperature=0.6, retries=3, timeout=180):
    """带重试：超时/网络抖动自动再来，最多3次"""
    import time
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}],
                       "temperature": temperature}).encode("utf-8")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(API, data=body, headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  [重试 {attempt}/{retries}] {str(e)[:60]}")
            time.sleep(3 * attempt)
    raise SystemExit("[!] API 连续失败，请检查网络后重跑（粗剪已缓存，不会重复扫描）")

data = json.load(open("粗剪.json", encoding="utf-8"))
dur, IV, frames = data["dur"], data["iv"], data["frames"]
game_frames = sorted([f for f in frames if f.get("type") == "游戏" and f.get("score", 0) >= 5],
                     key=lambda f: f["i"])
if not game_frames:
    raise SystemExit("[!] 粗剪里没有游戏画面帧，请检查 粗剪时间线.txt")

# ---------- 1. 让 AI 做剪辑决策 ----------
# 候选限长：帧太多时优先高分帧（防止 prompt 过长导致超时/输出截断）
picked = game_frames if len(game_frames) <= 110 else \
    sorted(sorted(game_frames, key=lambda f: -f.get("score", 0))[:110], key=lambda f: f["i"])
print(f"[细剪] 候选帧 {len(picked)}/{len(game_frames)}")
cand = "；".join(f"帧{f['i']}({int(f['i']*IV//60):02d}:{int(f['i']*IV%60):02d},{f['score']}分){f['desc']}"
                 for f in picked)
DECIDE = ("你是怀旧游戏解说视频的剪辑师。下面是粗剪后的游戏画面清单（时间,精彩度,内容）。"
    "任务：选 4-6 段组成一条 3-5 分钟的正片结构。要求："
    "1) 保留时间顺序（叙事符合游戏进程）；2) 相邻帧可合并为一段；"
    "3) 每段25-60秒（解说每段约25秒，段太长会被迫快进，宁短勿长）；"
    "4) 开头段要有代入感，结尾段适合收尾互动。"
    f"\n画面清单：{cand}"
    '\n只输出JSON：{"segments":[{"start_frame":帧号,"end_frame":帧号,"title":"这段讲什么"}]}，不要其他文字。')
print("[细剪] AI 决策叙事结构中...")
raw = re.sub(r"^```(json)?|```$", "", ask_llm([{"type": "text", "text": DECIDE}]).strip(), flags=re.M).strip()
plan = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])["segments"]

segs = []
def _fnum(v):
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else 0
for p in plan:
    a, b = _fnum(p.get("start_frame")), _fnum(p.get("end_frame"))
    if b < a:
        a, b = b, a
    t0 = max(0.0, a * IV - IV / 2)
    t1 = min(dur, (b + 1) * IV + IV / 2)
    if t1 - t0 < 20:
        continue
    segs.append({"t0": t0, "t1": min(t1, t0 + 150),
                 "frames": [f for f in game_frames if a <= f["i"] <= b], "title": p.get("title", "")})
if not segs:
    raise SystemExit("[!] 剪辑决策没有可用段")

# ---------- 2. 读取风格设定 ----------
style = ""
if os.path.exists("解说风格.txt"):
    raw_style = open("解说风格.txt", encoding="utf-8").read()
    style = "\n".join(l for l in raw_style.splitlines() if not l.startswith("#")).strip()

# ---------- 3. 开场钩子段（黄金3秒：全片最高分瞬间快闪）----------
best = max(game_frames, key=lambda f: f.get("score", 0))
hook_t0 = max(0.0, best["i"] * IV - 1.0)
hook = {"t0": hook_t0, "t1": min(dur, hook_t0 + 7.0),
        "frames": [best], "title": "开场钩子"}
segs = [hook] + segs
print(f"  开场钩子画面: {best['desc'][:30]}...（文案随全稿一起写）")

# ---------- 3.5 段内精抽帧：细剪选定后，对每段按4秒间隔重新抽帧细看 ----------
FINE_IV = 4

def fine_flow(i, s):
    ts, t = [], s["t0"] + FINE_IV / 2
    while t < s["t1"] and len(ts) < 8:
        ts.append(round(t, 1))
        t += FINE_IV
    files = []
    for k, tt in enumerate(ts):
        f = f"_fine_{i}_{k}.jpg"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(tt), "-i", "game.mp4",
                            "-frames:v", "1", "-q:v", "6", "-vf", "scale=512:-2", f],
                           capture_output=True)
        if r.returncode == 0 and os.path.exists(f):
            files.append(f)
    if not files:
        return None, None
    content = [{"type": "text", "text":
        ("这是成片中同一段的截图（按时间顺序，每4秒一帧）。逐张描述画面里正在发生什么"
         "（游戏内容细节：操作/事件/界面变化/数值）。"
         '只输出JSON：[{"n":序号,"desc":"一句话"}]，不要其他文字。')}]
    for k, f in enumerate(files):
        b64 = base64.b64encode(open(f, "rb").read()).decode()
        content.append({"type": "text", "text": f"图{k}:"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}})
    try:
        raw = re.sub(r"^```(json)?|```$", "", ask_llm(content).strip(), flags=re.M).strip()
        arr = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        arr = [a for a in arr if a.get("desc")][:len(files)]
        if not arr:
            return None, None
        return "；".join(a["desc"] for a in arr), ts[:len(arr)]
    except Exception as e:
        print(f"    段{i} 精抽失败，用粗剪描述兜底: {str(e)[:40]}")
        return None, None
    finally:
        for f in files:
            if os.path.exists(f):
                os.remove(f)

print("[精抽] 对每个正片段按4秒间隔重新抽帧细看...")

# ---------- 4. 全稿一次成文：整条叙事弧（起承转合+段间衔接）----------
flows, flow_items = [], {}          # flow_items[i] = (描述列表, 时间列表) 供句级锚定
for i, s in enumerate(segs):
    if i == 0:
        flows.append(f"【开场钩子｜画面】{best['desc']}")
        flow_items[0] = ([best["desc"]], [round(best["i"] * IV, 1)])
    else:
        desc, fts = fine_flow(i, s)
        if desc:
            flows.append(f"【段落{i}｜定位：{s['title']}｜画面流水】{desc}")
            flow_items[i] = (desc.split("；"), fts)
        else:
            ds = [f.get("desc", "") for f in s["frames"]]
            flows.append(f"【段落{i}｜定位：{s['title']}｜画面流水】" + "；".join(ds))
            flow_items[i] = (ds, [round(f["i"] * IV, 1) for f in s["frames"]][:len(ds)])

FULL = (
    "你是B站游戏考古视频的撰稿人。根据下面的分段画面素材，写出整支视频的解说稿。\n"
    "硬性要求：\n"
    f"1) 全稿是一条完整叙事线：开场悬念 → 展开 → 递进 → 收尾抛问；共{len(segs)}段按顺序输出，每段90-130字（约25秒配音）\n"
    "2) 第1段是开场钩子：不超过35字（约8秒配音），一句话勾住人立刻进正片，禁止铺陈\n"
    "3) 段与段之间必须有衔接：每段开头要接住上一段的结尾（因果/转折/推进），不许各说各的\n"
    "4) 画面流水只是素材，禁止照抄成报数流水账（不要罗列等级/金币/血量数值），"
    "把数值提炼成一两个有意义的对比或细节\n"
    "5) 冷静克制的旁白气质，用具体事实勾回忆，禁止直接抒情，禁止喊话\n"
    "6) 配音友好：数字写成汉字（「四十八血」不写「48血」），禁止英文单词和玩家ID（用「对手」代替），多用逗号制造停顿\n"
    "7) 严禁出现这些词：家人们、兄弟们、老铁、宝子、爷青回、回忆杀、DNA、泪目、扣1、谁懂啊、"
    "鸡皮疙瘩、绝绝子、yyds、关注我、一键三连、下期更精彩、满满的回忆\n"
    f'只输出JSON：{{"paras":["第1段全文","第2段全文",...]}}，数组元素个数必须={len(segs)}\n\n'
    "以下是解说风格设定，必须严格遵守（特别是禁用词表）：\n" + style)
print("[写稿] 全稿一次成文（含段间衔接）...")
raw = re.sub(r"^```(json)?|```$", "", ask_llm(
    [{"type": "text", "text": FULL + "\n\n" + "\n\n".join(flows)}]).strip(), flags=re.M).strip()
paras_raw = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])["paras"]
if len(paras_raw) != len(segs):
    print(f"[警告] AI 输出 {len(paras_raw)} 段 ≠ 需要 {len(segs)} 段，多删少补空")
    paras_raw = (paras_raw + [""] * len(segs))[:len(segs)]
paras = [re.sub(r"\s+", " ", p).strip() for p in paras_raw]
for i, t in enumerate(paras):
    title = segs[i].get("title", "")
    print(f"  段{i}[{title}] {t[:26]}...")

# ---------- 4.5 句级画面锚定：每句解说 ↔ 画面时间点（合成时逐句对齐画面）----------
def _split_sents(p):
    ss = [x.strip() for x in re.split(r"(?<=[。！？!?；;])", p) if x.strip()]
    out = []
    for x in ss:
        if out and len(x) < 4:
            out[-1] += x
        else:
            out.append(x)
    return out

anchors = []
for i in range(len(segs)):
    ss = _split_sents(paras[i]) if i < len(paras) else []
    descs, times = flow_items.get(i, ([], []))
    anch = None
    if 2 <= len(ss) <= 12 and descs and len(times) == len(descs):
        try:
            txt = ("给解说句子匹配画面时间点。\n解说句子：\n" +
                   "\n".join(f"句{j}：{t}" for j, t in enumerate(ss)) +
                   "\n画面条目（秒数=该画面在源视频的时刻）：\n" +
                   "\n".join(f"画面{j}（{times[j]:.0f}秒）：{d}" for j, d in enumerate(descs)) +
                   "\n按句子顺序，给每句选它描述的事件发生时的画面条目号（一句一个，可重复/跳跃）。"
                   '只输出JSON：{"a":[画面号,...]}，数组长度=句子数。')
            raw = re.sub(r"^```(json)?|```$", "", ask_llm(
                [{"type": "text", "text": txt}]).strip(), flags=re.M).strip()
            arr = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])["a"]
            if len(arr) == len(ss):
                anch = []
                for x in arr:
                    m = re.search(r"\d+", str(x))
                    k2 = max(0, min(len(times) - 1, int(m.group()) if m else 0))
                    anch.append(times[k2])
                anch = sorted(anch)
        except Exception as e:
            print(f"    段{i} 锚定失败（退回整段变速）: {str(e)[:40]}")
    anchors.append(anch)
    if anch:
        print(f"  段{i} 锚定{len(anch)}句 → " + ",".join(f"{t:.0f}s" for t in anch))
json.dump(anchors, open("anchors.json", "w", encoding="utf-8"), ensure_ascii=False)

# ---------- 5. 禁用词校验：出现即自动重写一次 ----------
banned = []
if style:
    in_ban = False
    for l in raw_style.splitlines():
        if "禁用词" in l:
            in_ban = True
            continue
        if l.startswith("###"):
            in_ban = False
        if in_ban and "、" in l:
            banned += [w.strip("： ").replace("禁用词表", "").replace("（出现即废稿）", "")
                       for w in l.split("、") if len(w.strip()) >= 2]
for j, t in enumerate(paras):
    bad = [w for w in banned if w and w in t]
    if bad:
        try:
            fixed = ask_llm([{"type": "text",
                "text": f"重写这段解说词，必须去掉这些词：{ '、'.join(bad) }。保持原风格和信息量，直接输出正文：\n{t}"}])
            paras[j] = re.sub(r"\s+", " ", fixed)
            print(f"  段{j} 检出禁用词 {bad} → 已重写")
        except Exception as e:
            print(f"  段{j} 重写失败（保留原文）: {str(e)[:40]}")

# ---------- 3. 落盘（保持与 01/03 兼容）----------
open("highlights.txt", "w", encoding="utf-8").write(
    "# 由 20_细剪.py 生成（剪辑决策）\n" +
    "\n".join(f"{int(s['t0']//60):02d}:{int(s['t0']%60):02d}-{int(s['t1']//60):02d}:{int(s['t1']%60):02d}" for s in segs) + "\n")

old = open("解说稿.txt", encoding="utf-8").read() if os.path.exists("解说稿.txt") else ""
tail = old.split("—————", 1)[1] if "—————" in old else ""
open("解说稿.txt", "w", encoding="utf-8").write(
    "\n\n".join(paras) + "\n" + (("\n—————" + tail) if tail else ""))

decisions = [f"段{i}  {int(s['t0']//60):02d}:{int(s['t0']%60):02d}-{int(s['t1']//60):02d}:{int(s['t1']%60):02d}  {s['title']}"
             for i, s in enumerate(segs)]
open("剪辑决策.txt", "w", encoding="utf-8").write("\n".join(decisions))

# ---------- 4. 按需配图：AI 判断每段需要什么老图 → 现场搜图验货 ----------
import importlib.util
spec = importlib.util.spec_from_file_location(
    "crawler", os.path.join(WORK, "40_爬素材.py"))
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)
AUTO_DIR = os.path.join(WORK, "old-materials", "auto")
os.makedirs(AUTO_DIR, exist_ok=True)
for f in os.listdir(AUTO_DIR):          # 清理上一期的配图
    os.remove(os.path.join(AUTO_DIR, f))
img_count = 0
for i, (s, txt) in enumerate(zip(segs, paras)):
    if i == 0:                          # 钩子段不配图
        continue
    try:
        kw = ask_llm([{"type": "text", "text":
            (f"这段解说词：{txt}\n\n要给这段配一张增强怀旧感的老图（游戏海报/精灵立绘/"
             "老版本界面/年代感截图）。输出一行搜索关键词，格式 KEYWORD:xxx，"
             "关键词必须含游戏名且具体到能搜到图。只输出这一行。")}])
        kw = re.split(r"[:：]", kw, 1)[-1].strip()[:40]
        paths = crawler.grab(kw, AUTO_DIR, limit=1, tag=f"素材_段{i}")
        if paths:
            img_count += 1
            print(f"  段{i} 配图: {kw} ✅")
        else:
            print(f"  段{i} 配图: {kw} 未找到合格图（该段无画中画）")
    except Exception as e:
        print(f"  段{i} 配图失败跳过: {str(e)[:50]}")
print(f"[配图] {img_count}/{len(segs)-1} 段已按需配图 → old-materials/auto/")

# ---------- 5. 自动生成投稿信息 ----------
try:
    info = ask_llm([{"type": "text", "text":
        ("根据这份B站怀旧游戏解说视频的解说稿，生成投稿信息，格式严格如下：\n"
         "标题候选：\n1.（数字冲击式）\n2.（悬念式）\n3.（冲突/反差式）\n"
         "简介：（80字内，含互动引导句）\n标签：（8个，空格分隔，不要#号）\n"
         "话题：（若与赛尔号/怀旧游戏相关，含 #赛尔号UP主共创计划 #怀旧游戏）\n\n解说稿：\n"
         + "\n".join(paras))}])
    open("投稿信息.txt", "w", encoding="utf-8").write(info)
    print("[OK] 投稿信息.txt 已生成（标题候选/简介/标签/话题）")
except Exception as e:
    print(f"[跳过] 投稿信息生成失败: {str(e)[:60]}")
print(f"[细剪完成] {len(segs)} 段结构 + 解说稿已生成 → 剪辑决策.txt / 解说稿.txt")
