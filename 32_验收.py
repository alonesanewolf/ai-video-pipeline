# -*- coding: utf-8 -*-
"""32 验收：成片 → 九宫格缩略图 + 音量/时长报告（10秒人工检查代替看全片）"""
import os, sys, re, subprocess
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if not os.path.exists("成片.mp4"):
    raise SystemExit("[!] 没有 成片.mp4")

r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", "成片.mp4"], capture_output=True, text=True)
dur = float(r.stdout.strip())

subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "成片.mp4",
                "-vf", f"fps=9/{dur:.2f},scale=320:180,tile=3x3",
                "-frames:v", "1", "验收图.jpg"], check=True)

r = subprocess.run(["ffmpeg", "-i", "成片.mp4", "-af", "volumedetect", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf-8", errors="ignore")
mean = re.search(r"mean_volume: ([-\d.]+) dB", r.stderr)
peak = re.search(r"max_volume: ([-\d.]+) dB", r.stderr)

print(f"[验收报告] 时长 {dur/60:.1f} 分钟")
print(f"  音量: 平均 {mean.group(1)}dB / 峰值 {peak.group(1)}dB"
      + ("  ⚠峰值>0可能爆音" if float(peak.group(1)) > -0.5 else "  ✅"))
print("  九宫格从左到右=片头到片尾：")
print("  ▸ 第1格应是钩子画面（游戏内高能瞬间，不能是桌面）")
print("  ▸ 各格都应是游戏画面，不应出现大片桌面/加载")
print("  ▸ 老图出现时右下角会有画中画")
os.startfile("验收图.jpg")
print("[OK] 验收图.jpg 已打开")
