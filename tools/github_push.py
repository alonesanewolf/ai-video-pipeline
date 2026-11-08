# -*- coding: utf-8 -*-
"""git push 被墙时的备用发布通道：走 GitHub Git Data API 单提交推送全部文件
用法：python tools/github_push.py [owner/repo]   （默认读 AVP_REPO 环境变量）
需要 gh CLI 已登录（取 token）"""
import base64, json, subprocess, urllib.request, os, sys

REPO = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AVP_REPO", "alonesanewolf/ai-video-pipeline")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
assert token, "请先 gh auth login"

def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("https://api.github.com" + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "avp-push"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            return json.loads(raw) if raw else {}
        except Exception as e:
            print(f"  重试 {attempt+1}/3: {str(e)[:60]}")
            if attempt == 2:
                raise

tree = []
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in (".git", "docs")]
    for f in fn:
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        blob = api("POST", f"/repos/{REPO}/git/blobs", {"content": b64, "encoding": "base64"})
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("blob:", rel)

new_tree = api("POST", f"/repos/{REPO}/git/trees", {"tree": tree})
commit = api("POST", f"/repos/{REPO}/git/commits", {"message": "sync from local", "tree": new_tree["sha"]})
try:
    api("GET", f"/repos/{REPO}/git/ref/heads/main")
    api("PATCH", f"/repos/{REPO}/git/refs/heads/main", {"sha": commit["sha"], "force": True})
except Exception:
    api("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/main", "sha": commit["sha"]})
print("== 已推送", commit["sha"][:8], "==")
