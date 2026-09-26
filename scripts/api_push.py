#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 github.com 的 git 端口不通时，用 GitHub Git Data API 把本地改动推成一个提交。

用法（在仓库目录里执行）：
    python api_push.py --repo owner/name --token <token> [--base <远端当前 commit>]

流程：取远端 HEAD → 生成 base64 blob → 建 tree（base_tree=远端 tree）→ 建 commit → 更新 ref。
内容与本地工作区一致；提交作者用 git 的 user.name/user.email。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def call(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + url, data=data, method=method)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "api-push")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise SystemExit("HTTP %s %s %s\n%s" % (e.code, method, url, detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--token", required=True)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--message", required=True)
    ap.add_argument("--files", nargs="*", help="要提交的文件（默认取 git 未提交/已修改的全部）")
    args = ap.parse_args()

    # 1) 远端 HEAD
    ref = call("GET", "/repos/%s/git/ref/heads/%s" % (args.repo, args.branch), args.token)
    head = ref["object"]["sha"]
    commit = call("GET", "/repos/%s/git/commits/%s" % (args.repo, head), args.token)
    base_tree = commit["tree"]["sha"]
    print("远端 HEAD: %s（tree %s）" % (head[:7], base_tree[:7]))

    def git_names(*argv):
        # 用 -z 取 NUL 分隔的文件名，避免中文名被 git 转义成 \344\275... 形式
        out = subprocess.run(["git", *argv, "-z"], capture_output=True, text=True).stdout
        return [x for x in out.split("\0") if x]

    files = args.files or git_names("diff", "--name-only", head, "HEAD")
    files += git_names("ls-files", "--others", "--exclude-standard")
    files = sorted({f for f in files if os.path.isfile(f)})
    if not files:
        print("没有需要提交的文件")
        return 0
    print("要提交 %d 个文件:" % len(files))
    for f in files:
        print("   ", f)

    # 2) 逐个生成 blob
    tree = []
    for f in files:
        with open(f, "rb") as fh:
            blob = call("POST", "/repos/%s/git/blobs" % args.repo, args.token,
                        {"content": base64.b64encode(fh.read()).decode(), "encoding": "base64"})
        tree.append({"path": f, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("   blob %s  %s" % (blob["sha"][:7], f))

    # 3) 新 tree
    new_tree = call("POST", "/repos/%s/git/trees" % args.repo, args.token,
                    {"base_tree": base_tree, "tree": tree})
    print("新 tree: %s" % new_tree["sha"][:7])

    # 4) 新 commit
    name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip() or "voice-workshop"
    email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip() or "noreply@example.com"
    new_commit = call("POST", "/repos/%s/git/commits" % args.repo, args.token,
                      {"message": args.message, "tree": new_tree["sha"], "parents": [head],
                       "author": {"name": name, "email": email},
                       "committer": {"name": name, "email": email}})
    print("新 commit: %s" % new_commit["sha"][:7])

    # 5) 更新分支
    call("PATCH", "/repos/%s/git/refs/heads/%s" % (args.repo, args.branch), args.token,
         {"sha": new_commit["sha"], "force": False})
    print("✅ 已更新 %s → %s" % (args.branch, new_commit["sha"][:7]))
    print("提示：等 github.com 的 git 端口恢复后，执行 git fetch && git reset --hard origin/%s 对齐本地" % args.branch)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
