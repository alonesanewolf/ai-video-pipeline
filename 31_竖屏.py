# -*- coding: utf-8 -*-
"""31 竖屏：成片.mp4 → 竖屏版.mp4（9:16 中央裁切，抖音/西瓜用）"""
import os, sys, subprocess
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if not os.path.exists("成片.mp4"):
    raise SystemExit("[!] 先合成出 成片.mp4 再跑竖屏版")
r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "成片.mp4",
    "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
    "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "25",
    "-c:a", "aac", "-b:a", "160k", "竖屏版.mp4"],
    capture_output=True, text=True, encoding="utf-8", errors="ignore")
if r.returncode != 0:
    print(r.stderr[-400:])
    raise SystemExit("[!] 竖屏版合成失败")
print("[OK] 竖屏版.mp4 已生成（1080x1920，抖音直接传）")
