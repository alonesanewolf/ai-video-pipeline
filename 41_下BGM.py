# -*- coding: utf-8 -*-
"""41 下BGM：incompetech 免版权曲库（Kevin MacLeod, CC-BY 4.0）
下载 → bgm.mp3，03_剪辑.py 合成时自动垫底。用法：python 41_下BGM.py [序号]"""
import os, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.chdir(WORK)
BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
TRACKS = [
    ("Heartwarming.mp3",                    "温暖钢琴（怀旧解说首选）"),
    ("Wallpaper.mp3",                       "轻快微复古"),
    ("Carefree.mp3",                        "悠闲日常"),
    ("Porch%20Swing%20Days%20-%20faster.mp3", "门廊秋千·快版（童年午后感）"),
    ("Daily%20Beetle.mp3",                  "俏皮轻松"),
    ("Sneaky%20Snitch.mp3",                 "滑头搞事（整活段）"),
    ("Fluffing%20a%20Duck.mp3",             "傻气欢乐（沙雕向）"),
    ("Wisps%20of%20Whorls.mp3",             "空灵叙事（回忆杀段落）"),
]

print("[免版权 BGM 曲库]（Kevin MacLeod / CC-BY 4.0，可投稿可商用）")
for i, (f, d) in enumerate(TRACKS, 1):
    print(f"  {i}. {d}")

idx = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
f, d = TRACKS[idx - 1]
print(f"\n下载: {d} ...")
req = urllib.request.Request(BASE + f, headers={"User-Agent": "Mozilla/5.0"})
open("bgm.mp3", "wb").write(urllib.request.urlopen(req, timeout=120).read())
print(f"[完成] bgm.mp3 已就位（{os.path.getsize('bgm.mp3')//1024}KB）→ 合成时自动垫底")
print("换曲子：python 41_下BGM.py 序号")
