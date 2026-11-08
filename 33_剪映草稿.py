# -*- coding: utf-8 -*-
"""33 剪映草稿：把成片时间线重建为剪映专业版可编辑草稿
画面（原速段+变速）+ 解说 + 字幕 + BGM 四轨，生成后打开剪映即可精修
用法：python 33_剪映草稿.py [草稿名]"""
import os, sys, json, re, shutil
sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.environ.get("AVP_VECTCUT", r"D:\stream-tools\VectCutAPI"))

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
DRAFT_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                          "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
TPL = os.path.join(os.environ.get("AVP_VECTCUT", r"D:\stream-tools\VectCutAPI"), "template_jianying_10_2")

import pyJianYingDraft as draft
from pyJianYingDraft import trange, tim

us = lambda s: tim(f"{s}s")          # 秒 → 微秒

os.chdir(WORK)

def parse_t(t):
    t = t.strip()
    if ":" in t:
        parts = [float(x) for x in t.split(":")]
        return sum(x * 60 ** i for i, x in enumerate(reversed(parts)))
    return float(t)

meta = json.load(open("segments.json", encoding="utf-8"))
hl = [l.strip() for l in open("highlights.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
segs = []
for l in hl:
    if "-" in l:
        a, b = l.split("-", 1)
        segs.append((parse_t(a), parse_t(b)))
    else:
        a = parse_t(l)
        segs.append((a, a + 30.0))
n = min(len(segs), len(meta))
if not os.path.exists("game.mp4") or not meta:
    raise SystemExit("[!] 缺少 game.mp4 或 segments.json，先跑完整流程")

W, H = 1680, 1050
script = draft.Script_file(W, H, fps=30)
script.add_track(draft.Track_type.video, "画面")
script.add_track(draft.Track_type.audio, "解说")
script.add_track(draft.Track_type.text, "字幕")
has_bgm = os.path.exists("bgm.mp3")
if has_bgm:
    script.add_track(draft.Track_type.audio, "BGM")

t = 0.0
for i in range(n):
    a, b = segs[i]
    vdur = b - a
    adur = meta[i]["dur"]
    k = max(0.5, min(2.0, adur / vdur))
    # 画面：源区间原样引用，变速到配音时长（剪映里可手动再调）
    vs = draft.Video_segment(
        draft.Video_material("video", path=os.path.join(WORK, "game.mp4")),
        trange(us(t), us(adur)),
        source_timerange=trange(us(a), us(vdur)),
        speed=k, volume=0.12)
    script.add_segment(vs, "画面")
    # 解说
    aus = draft.Audio_segment(
        draft.Audio_material(path=meta[i]["file"]),
        trange(us(t), us(adur)), volume=1.0)
    script.add_segment(aus, "解说")
    # 字幕（逐句 + 呼吸间隙）
    tt = t
    sents = meta[i].get("sents") or [{"text": meta[i]["text"], "dur": adur, "gap": 0}]
    for s in sents:
        d = min(s["dur"], t + adur - tt)
        ts = draft.Text_segment(
            s["text"], trange(us(tt), us(max(d, 0.1))),
            style=draft.Text_style(size=8.0, bold=True),
            border=draft.Text_border(color="#000000", width=60))
        script.add_segment(ts, "字幕")
        tt += s["dur"] + s.get("gap", 0)
    t += adur
    print(f"  段{i}: {a:.0f}s-{b:.0f}s → 时间线 {t:.1f}s (x{k:.2f})")

total = t
if has_bgm:
    bs = draft.Audio_segment(
        draft.Audio_material(path=os.path.join(WORK, "bgm.mp3")),
        trange(us(0), us(total)),
        source_timerange=trange(us(0), us(total)),
        volume=0.18)
    script.add_segment(bs, "BGM")

# 落盘到剪映草稿目录
name = sys.argv[1] if len(sys.argv) > 1 else "AI成片精修_" + \
    __import__("datetime").datetime.now().strftime("%m%d_%H%M")
dst = os.path.join(DRAFT_ROOT, name)
os.makedirs(dst, exist_ok=True)
for f in ("draft_meta_info.json", "draft_agency_config.json", "draft_biz_config.json",
          "draft_settings", "attachment_pc_common.json"):
    src = os.path.join(TPL, f)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(dst, f))
script.dump(os.path.join(dst, "draft_content.json"))
script.dump(os.path.join(dst, "draft_info.json"))
print(f"[OK] 草稿已生成：{dst}")
print(f"  时间线 {total:.0f}s / {n} 段 / 画面+解说+字幕{' +BGM' if has_bgm else ''}")
print("  ▶ 打开剪映专业版 → 首页草稿列表即可看到，可直接精修导出")
