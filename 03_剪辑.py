# -*- coding: utf-8 -*-
"""03 剪辑引擎 v3：配音驱动剪辑
每段解说音频 = 该段画面的最终时长（视频裁剪/变速/定格到与配音严格对齐）
字幕由解说文本直出（零错字），逐段烧录后无损拼接"""
import os, re, json, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.chdir(WORK)
VENC = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-r", "60"]

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        print(r.stderr[-1200:]); raise SystemExit("[失败] " + " ".join(cmd[:8]))

def probe(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", f], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("[失败] ffprobe " + f)
    return float(r.stdout.strip())

def parse_t(t):
    t = t.strip()
    if ":" in t:
        parts = [float(x) for x in t.split(":")]
        return sum(x * 60**i for i, x in enumerate(reversed(parts)))
    return float(t)

def fmt(sec):
    sec = max(0.0, sec)
    h, sec = divmod(int(sec), 3600); m, sec = divmod(sec, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{int(round((sec % 1) * 1000)):03d}"

# ---------- 1. 精华段 + 配音段 ----------
hl = [l.strip() for l in open("highlights.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
if not hl:
    raise SystemExit("[!] highlights.txt 没有时间段（每行如 03:20-06:00）")
segs = []
for l in hl:
    if "-" in l:
        a, b = l.split("-", 1); segs.append((parse_t(a), parse_t(b)))
    else:
        a = parse_t(l); segs.append((a, a + 30.0))

meta = json.load(open("segments.json", encoding="utf-8"))
n = min(len(segs), len(meta))
if len(segs) != len(meta):
    print(f"[警告] 画面段 {len(segs)} 个 vs 解说段 {len(meta)} 个，取前 {n} 段配对")
print(f"[剪辑] {n} 段：画面时长对齐配音时长")

# ---------- 2. 逐段处理 ----------
import glob
def seg_img(i):
    """该段按需配图（细剪阶段生成于 old-materials/auto/素材_段N_*）"""
    p = sorted(glob.glob(os.path.join(WORK, "old-materials", "auto", f"素材_段{i}_*")))
    return p[0] if p else None

def wrap(s, n=16):
    out = []
    while len(s) > n:
        cut = n
        for p in ("，", "、", "；", " "):
            r = s.rfind(p, 0, n + 1)
            if r > n // 2:
                cut = r + 1
                break
        out.append(s[:cut].strip())
        s = s[cut:]
    if s.strip():
        out.append(s.strip())
    return out

def srt_for(text, dur, path, sents=None):
    """sents 有值→用逐句真实时长（帧级对齐）；否则按字数比例兜底"""
    if sents:
        items = [(s["text"], s["dur"]) for s in sents]
    else:
        raw = [s.strip() for s in re.split(r"[。！？\n]+", text) if len(s.strip()) >= 4]
        total = sum(len(s) for s in raw) or 1
        items = [(s, dur * len(s) / total) for s in raw]
    t, lines = 0.0, []
    for k, (txt, d) in enumerate(items, 1):
        end = min(t + d, dur - 0.05)
        lines.append(f"{k}\n{fmt(t)} --> {fmt(end)}\n" + "\n".join(wrap(txt)) + "\n")
        t += d + (sents[k - 1].get("gap", 0) if sents else 0)
    open(path, "w", encoding="utf-8").write("\n".join(lines))

total_before = 0.0
for i in range(n):
    a, b = segs[i]
    vdur = b - a
    adur = meta[i]["dur"]
    sents = meta[i].get("sents")
    srt_for(meta[i]["text"], adur, f"_srt{i}.srt", sents)

    # 句级锚定模式：每句解说对应一段画面切片（讲到哪句，画面就在哪句的事件上）
    anch = meta[i].get("anchors")
    seg_file = None
    if (anch and sents and len(anch) == len(sents)
            and all(isinstance(x, (int, float)) for x in anch)
            and all(anch[j] <= anch[j + 1] + 0.01 for j in range(len(anch) - 1))):
        try:
            starts, cum = [], 0.0
            for s in sents:
                starts.append(cum)
                cum += s["dur"] + s.get("gap", 0)
            bounds = [max(a, min(b - 0.4, float(x))) for x in anch]
            for j in range(1, len(bounds)):       # 相邻锚点强制最小源间隔，避免极限变速
                if bounds[j] < bounds[j - 1] + 1.2:
                    bounds[j] = min(b - 0.4, bounds[j - 1] + 1.2)
            drift = 0.0
            for j, s in enumerate(sents):
                s0 = bounds[j]
                s1 = bounds[j + 1] if j + 1 < len(bounds) else b
                if s1 <= s0 + 0.4:
                    s1 = s0 + 0.4
                t0n = starts[j] - drift
                t1n = (starts[j + 1] - drift) if j + 1 < len(sents) else adur
                tdur = max(0.3, t1n - t0n)          # 该句配音时长（末片吸收累计漂移）
                spc = max(0.5, min(2.2, (s1 - s0) / tdur))
                ch = f"_ch_{i}_{j}.mp4"
                run(["ffmpeg", "-y", "-v", "error", "-ss", f"{s0:.2f}", "-t", f"{s1 - s0:.2f}",
                     "-i", "game.mp4", "-vf", f"setpts=PTS/{spc:.4f}",
                     "-af", f"atempo={spc:.4f}", *VENC, "-c:a", "aac", "-b:a", "128k",
                     "-ar", "48000", ch])
                drift += probe(ch) - tdur
            with open(f"_cl{i}.txt", "w", encoding="utf-8") as fh:
                for j in range(len(sents)):
                    fh.write(f"file '_ch_{i}_{j}.mp4'\n")
            seg_file = f"_segs{i}.mp4"
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", f"_cl{i}.txt", "-c", "copy", seg_file])
            outdur = probe(seg_file)
            print(f"  段{i} 句级锚定: {len(sents)} 片（画面逐句跟随解说）")
        except SystemExit:
            raise
        except Exception as e:
            print(f"  段{i} 锚定切片失败，退回整段变速: {str(e)[:60]}")
            seg_file = None

    if seg_file:
        src_in = ["-i", seg_file]
        vparts, aparts = [], ["apad"]
    else:
        # 时间倍率：k=画面要拉长/压缩到配音时长的倍数，限 [0.5, 2]
        k = max(0.5, min(2.0, adur / vdur))
        outdur = vdur * k
        src_in = ["-ss", str(a), "-to", str(b), "-i", "game.mp4"]
        vparts = [f"setpts=PTS*{k:.4f}"] if abs(k - 1) > 0.03 else []
        aparts = ([f"atempo={1/k:.4f}"] if abs(k - 1) > 0.03 else []) + ["apad"]

    if outdur < adur - 0.1:                       # 慢放后仍不足 → 定格末帧补齐
        vparts.append(f"tpad=stop_mode=clone:stop_duration={adur - outdur + 0.3:.2f}")
    vparts.append("subtitles=_srt%d.srt:force_style='FontSize=17,Bold=1,Outline=2,Shadow=1,MarginV=16'" % i)
    vparts.append(f"fade=t=in:st=0:d=0.12,fade=t=out:st={max(0.0, adur - 0.25):.2f}:d=0.25")

    # BGM 支持：workflow 里放一个 bgm.mp3 就自动垫底（循环+压低+跨段连续）
    has_bgm = os.path.exists("bgm.mp3")
    if has_bgm:
        fc = (f"[0:v]{','.join(vparts)}[v0];"
              f"[0:a]volume=0.12,{','.join(aparts)}[ga];"
              f"[1:a]volume=1.8,apad[na];"
              f"[2:a]volume=0.18,apad[bg];"
              f"[na][bg]amix=inputs=2:duration=longest:normalize=0[nb];"
              f"[ga][nb]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.79[aout]")
        extra_in = ["-ss", f"{total_before % 120:.2f}", "-stream_loop", "-1", "-i", "bgm.mp3"]
    else:
        fc = (f"[0:v]{','.join(vparts)}[v0];"
              f"[0:a]volume=0.12,{','.join(aparts)}[ga];"
              f"[1:a]volume=1.8,apad[na];"
              f"[ga][na]amix=inputs=2:duration=longest:dropout_transition=0,alimiter=limit=0.79[aout]")
        extra_in = []

    # 画中画老图：细剪阶段按需配到哪段就插哪段
    img_idx = 2 + (1 if has_bgm else 0)
    vmap = "[v0]"
    img = seg_img(i) if i > 0 else None
    if img:
        extra_in += ["-loop", "1", "-i", img]
        D = min(adur - 0.6, adur * 0.7)
        fc += (f";[{img_idx}:v]scale='min(iw*0.30,400)':-2,format=rgba,"
               f"fade=t=in:st=0.4:d=0.4:alpha=1,fade=t=out:st={max(0.5, D-0.4):.2f}:d=0.4:alpha=1[ov];"
               f"[v0][ov]overlay=W-w-24:H-h-90:enable='between(t,0.4,{max(0.9, D):.2f})'[vout]")
        vmap = "[vout]"
    if img:
        print(f"  段{i} 画中画: {os.path.basename(img)}")
    run(["ffmpeg", "-y", "-v", "error",
         *src_in,
         "-i", meta[i]["file"], *extra_in,
         "-filter_complex", fc, "-map", vmap, "-map", "[aout]",
         "-t", str(adur), *VENC, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         f"_seg{i}.mp4"])
    total_before += adur
    if seg_file:
        print(f"  段{i}: 配音{adur:.0f}s（句级锚定）")
        os.remove(seg_file)
        if os.path.exists(f"_cl{i}.txt"):
            os.remove(f"_cl{i}.txt")
        for f2 in glob.glob(f"_ch_{i}_*.mp4"):
            os.remove(f2)
    else:
        print(f"  段{i}: 画面{vdur:.0f}s → 配音{adur:.0f}s (x{k:.2f})")

# ---------- 3. 无损拼接 ----------
with open("_list.txt", "w", encoding="utf-8") as f:
    for i in range(n):
        f.write(f"file '_seg{i}.mp4'\n")
run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "_list.txt",
     "-c", "copy", "成片.mp4"])
for i in range(n):
    for f in (f"_seg{i}.mp4", f"_srt{i}.srt"):
        if os.path.exists(f):
            os.remove(f)
os.remove("_list.txt")
print(f"[完成] 成片.mp4 = {probe('成片.mp4'):.0f}s（声画逐段对齐）")
