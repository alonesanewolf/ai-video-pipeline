# -*- coding: utf-8 -*-
"""40 爬素材 v3：grab() 供其他脚本按需调用；命令行也可手动用
用法：python 40_爬素材.py 关键词... [数量]
流程：搜图→下载候选→GLM验货→只留真相关的"""
import os, re, sys, json, base64, urllib.request, urllib.parse, hashlib
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.environ.get("AVP_WORK", r"D:\stream-tools\workflow")
os.makedirs(os.path.join(WORK, "old-materials"), exist_ok=True)
os.chdir(WORK)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def search_bing_images(query, n):
    q = urllib.parse.quote(query)
    urls = []
    for host in ("https://www.bing.com", "https://cn.bing.com"):
        try:
            html = fetch(f"{host}/images/async?q={q}&first=0&count={n}&mmasync=1&adlt=moderate").decode("utf-8", "ignore")
            for m in re.findall(r'm="([^"]+)"', html):
                try:
                    u = json.loads(m.replace("&quot;", '"')).get("murl", "")
                    if u.startswith("http") and u not in urls:
                        urls.append(u)
                except Exception:
                    pass
            for u in re.findall(r'"murl\\?":\\?"(http[^"\\]+)', html):
                if u not in urls:
                    urls.append(u)
            if len(urls) >= n:
                break
        except Exception:
            pass
    return urls

def _llm(content):
    import time
    key = open("glm_key.txt", encoding="utf-8").read().strip().splitlines()[-1].strip()
    body = json.dumps({"model": "glm-5.3-flashx", "messages": [{"role": "user", "content": content}],
                       "temperature": 0.2}).encode("utf-8")
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request("https://open.bigmodel.cn/api/paas/v4/chat/completions",
                data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"    [重试 {attempt}/3] {str(e)[:50]}")
            time.sleep(3 * attempt)
    raise Exception("API 连续3次失败")

def _verify(files, query):
    """GLM 验货，返回 [(name, rel, why)] 仅相关项"""
    kept = []
    for start in range(0, len(files), 5):
        batch = files[start:start + 5]
        content = [{"type": "text",
                    "text": (f"判断每张图是否与「{query}」真正相关（游戏截图/海报/角色图才算相关，"
                             "新闻配图但内容无关=不相关）。"
                             '只输出JSON：[{"n":图序号,"rel":相关度0-10,"why":"5字内原因"}]')}]
        for j, name in enumerate(batch):
            b64 = base64.b64encode(open(name, "rb").read()).decode()
            content.append({"type": "text", "text": f"图{start+j}:"})
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}})
        try:
            raw = re.sub(r"^```(json)?|```$", "", _llm(content).strip(), flags=re.M).strip()
            for v in json.loads(raw[raw.index("["):raw.rindex("]") + 1]):
                idx = int(v.get("n", -1))
                if 0 <= idx < len(files) and float(v.get("rel", 0)) >= 6:
                    kept.append((files[idx], float(v["rel"]), v.get("why", "ok")))
        except Exception:
            pass
    return kept

def grab(query, out_dir, limit=1, tag=None):
    """按需抓图：搜图→候选→验货→命名保存，返回成功保存的路径列表"""
    os.makedirs(out_dir, exist_ok=True)
    cand_n = limit * 4 + 4
    urls = search_bing_images(query, cand_n)
    tmp = []
    for k, u in enumerate(urls):
        if len(tmp) >= cand_n:
            break
        try:
            data = fetch(u)
            if len(data) < 15000:
                continue
            ext = ".png" if u.lower().split("?")[0].endswith(".png") else ".jpg"
            name = os.path.join(out_dir, f"_c{hashlib.md5(u.encode()).hexdigest()[:6]}{ext}")
            open(name, "wb").write(data)
            tmp.append(name)
        except Exception:
            pass
    if not tmp:
        return []
    kept = sorted(_verify(tmp, query), key=lambda x: -x[1])[:limit]
    saved = []
    for k, (name, rel, why) in enumerate(kept):
        safe_why = re.sub(r'[\\/:*?"<>|\s]', "", why)[:8] or "img"
        new = os.path.join(out_dir, f"{tag or re.sub(chr(92)+'s','_',query)[:16]}_{k+1:02d}_{safe_why}{os.path.splitext(name)[1]}")
        os.replace(name, new)
        saved.append(new)
    for name in tmp:                      # 清理未选中的候选
        if os.path.exists(name):
            os.remove(name)
    return saved

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python 40_爬素材.py 关键词... [数量]（AI验货后只留真相关的）")
        sys.exit(0)
    args = sys.argv[1:]
    limit = int(args[-1]) if args[-1].isdigit() else 8
    query = " ".join(args if not args[-1].isdigit() else args[:-1])
    print(f"[爬素材] {query} → old-materials\\（目标 {limit} 张，AI 验货）")
    out = os.path.join(WORK, "old-materials")
    saved = grab(query, out, limit=limit)
    for f in saved:
        print(f"  ✅ {os.path.basename(f)}")
    print(f"[完成] {len(saved)} 张 → {out}")
    os.startfile(out)
