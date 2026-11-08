# -*- coding: utf-8 -*-
"""01 配音 v4：解说稿分段 → 逐句 TTS → 拼回段音频
segments.json 记录每句精确时长，03 用它生成帧级对齐字幕"""
import os, re, json, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
ROOT = os.environ.get("AVP_TTS_ROOT", r"D:\stream-tools\IndexTTS2")
VOICE = os.environ.get("AVP_VOICE", r"D:\stream-tools\my-videos\voice_sample.mp3")

os.chdir(ROOT)
text = open(os.path.join(WORK, "解说稿.txt"), encoding="utf-8").read()
text = text.split("—————")[0].strip()
if not text:
    sys.exit("[!] 解说稿.txt 是空的")

paras = [re.sub(r"[【】]", "，", p).strip() for p in re.split(r"\n\s*\n", text)]
paras = [p for p in paras if len(p) >= 15]
if not paras:
    sys.exit("[!] 解说稿分段失败：请用空行分隔各段")
print(f"[配音] 共 {len(paras)} 段，逐句合成中（比整段慢约1分钟，换来字幕精确对齐）")

from indextts.infer_v2_5 import IndexTTS2
tts = IndexTTS2(
    model_dir="checkpoints",
    cfg_path=os.path.join("checkpoints", "config.yaml"),
    use_deepspeed=False, use_cuda_kernel=False, use_accel=False,
    use_torch_compile=False, use_qwen_emo=True, use_bf16=True,
)

def probe(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", f], capture_output=True, text=True)
    return float(r.stdout.strip())

def split_sents(p):
    sents = [s.strip() for s in re.split(r"(?<=[。！？!?；;])", p) if s.strip()]
    out = []
    for s in sents:                       # 太短的句子并进前一句，避免 TTS 破音
        if out and len(s) < 4:
            out[-1] += s
        else:
            out.append(s)
    return out

meta = []
GAP = 0.18                            # 句间呼吸静音（秒）
for i, p in enumerate(paras):
    sents = split_sents(p)
    files = []
    for j, s in enumerate(sents):
        f = os.path.join(WORK, f"_s{i}_{j}.wav")
        tts.infer(spk_audio_prompt=VOICE, text=s, output_path=f, lang="zh_CN")
        files.append(f)
    # 句间垫静音 + 统一重采样后拼接（消除硬拼接的机械断裂感）
    inputs, chains, idx = [], [], 0
    for j, f in enumerate(files):
        inputs += ["-i", f]
        chains.append(f"[{idx}:a]aformat=sample_rates=24000:channel_layouts=mono[a{idx}]")
        idx += 1
        if j < len(files) - 1:
            inputs += ["-f", "lavfi", "-t", f"{GAP}", "-i", "anullsrc=r=24000:cl=mono"]
            chains.append(f"[{idx}:a]aformat=sample_rates=24000:channel_layouts=mono[a{idx}]")
            idx += 1
    order = "".join(f"[a{k}]" for k in range(idx))
    fc = ";".join(chains) + f";{order}concat=n={idx}:v=0:a=1[out]"
    seg = os.path.join(WORK, f"narration_seg{i}.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-ar", "24000", "-c:a", "pcm_s16le", seg], check=True)
    durs = [probe(f) for f in files]
    meta.append({"file": seg, "text": p,
                 "dur": sum(durs) + GAP * (len(sents) - 1),
                 "sents": [{"text": s, "dur": d,
                            "gap": (GAP if j < len(sents) - 1 else 0)}
                           for j, (s, d) in enumerate(zip(sents, durs))]})
    print(f"  段{i}: {len(sents)}句 / {meta[-1]['dur']:.1f}s（含句间呼吸）")
    for f in files:
        os.remove(f)

anch = None
if os.path.exists(os.path.join(WORK, "anchors.json")):
    try:
        anch = json.load(open(os.path.join(WORK, "anchors.json"), encoding="utf-8"))
    except Exception:
        anch = None
if anch and len(anch) == len(meta):
    used = 0
    for i, m in enumerate(meta):
        if anch[i] and len(anch[i]) == len(m["sents"]):
            m["anchors"] = anch[i]
            used += 1
    print(f"[OK] 句级画面锚定并入 {used}/{len(meta)} 段（有锚段逐句对齐画面）")
    os.remove(os.path.join(WORK, "anchors.json"))

json.dump(meta, open(os.path.join(WORK, "segments.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[OK] 总时长 {sum(m['dur'] for m in meta):.0f}s → segments.json（含逐句时长）")
