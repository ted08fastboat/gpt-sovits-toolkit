#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 GPT-SoVITS 中文推理所需的预训练模型（跨平台，hf-mirror 优先）。

用法:
  fetch_assets.py --repo /repo [--only-missing] [--mirror https://hf-mirror.com]

会写入:
  <repo>/GPT_SoVITS/pretrained_models/...   （BERT、HuBERT、v2Pro、v2、sv）
  <repo>/GPT_SoVITS/text/G2PWModel/         （中文多音字消歧）
  <repo>/GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin（语种检测）
  <repo>/nltk_data/                         （英文 G2P 备用）
"""
import argparse
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile

MODEL_FILES = [
    "chinese-hubert-base/config.json",
    "chinese-hubert-base/preprocessor_config.json",
    "chinese-hubert-base/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/config.json",
    "chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/tokenizer.json",
    "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "gsv-v2final-pretrained/s2G2333k.pth",
    "s1v3.ckpt",
    "v2Pro/s2Gv2Pro.pth",
    "v2Pro/s2Gv2ProPlus.pth",
    "sv/pretrained_eres2netv2w24s4ep4.ckpt",
]
EXTRA_REPO = "XXXXRT/GPT-SoVITS-Pretrained"
FASTTEXT_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.1f%s" % (n, u)
        n /= 1024.0


def download(url, dest, retries=3, timeout=60):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, retries + 1):
        tmp = dest + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                last = 0.0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and time.time() - last > 3:
                            last = time.time()
                            print("\r    %-46s %5.1f%% (%s/%s)" % (
                                os.path.basename(dest)[:46], done * 100.0 / total, human(done), human(total)),
                                end="", flush=True)
            if total and os.path.getsize(tmp) != total:
                raise IOError("大小不符")
            if total:
                print("\r    %-46s 100.0%% (%s)          " % (os.path.basename(dest)[:46], human(os.path.getsize(tmp))))
            os.replace(tmp, dest)
            return True
        except Exception as e:  # noqa: BLE001
            print("\r    [!] 第 %d 次失败: %s          " % (attempt, e))
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            time.sleep(3)
    return False


def download_any(urls, dest):
    for u in urls:
        if download(u, dest):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="GPT-SoVITS 仓库根目录")
    ap.add_argument("--mirror", default=os.environ.get("HF_ENDPOINT", "https://hf-mirror.com"))
    ap.add_argument("--only-missing", action="store_true", help="只下载缺失的文件（默认行为）")
    ap.add_argument("--force", action="store_true", help="即使存在也重新下载")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    pm = os.path.join(repo, "GPT_SoVITS", "pretrained_models")
    mirrors = [args.mirror.rstrip("/"), "https://huggingface.co"]
    os.makedirs(pm, exist_ok=True)

    ok = True
    print("== 主模型（lj1995/GPT-SoVITS）==")
    for rel in MODEL_FILES:
        dest = os.path.join(pm, rel)
        if os.path.exists(dest) and os.path.getsize(dest) > 1024 and not args.force:
            print("  已存在: %s" % rel)
            continue
        enc = urllib.parse.quote(rel)
        print("  下载: %s" % rel)
        if not download_any(["%s/lj1995/GPT-SoVITS/resolve/main/%s" % (m, enc) for m in mirrors], dest):
            print("  ❌ 失败: %s" % rel)
            ok = False

    g2pw = os.path.join(repo, "GPT_SoVITS", "text", "G2PWModel")
    if not os.path.isdir(g2pw) or args.force:
        print("== G2PWModel（中文多音字，约 590MB）==")
        z = "/tmp/_G2PWModel.zip"
        if download_any(["%s/%s/resolve/main/G2PWModel.zip" % (m, EXTRA_REPO) for m in mirrors], z):
            print("  解压…")
            with zipfile.ZipFile(z) as zf:
                zf.extractall(os.path.join(repo, "GPT_SoVITS", "text"))
            os.remove(z)
            if not os.path.isdir(g2pw):
                for d in os.listdir(os.path.join(repo, "GPT_SoVITS", "text")):
                    if d.lower().startswith("g2pw"):
                        os.rename(os.path.join(repo, "GPT_SoVITS", "text", d), g2pw)
                        break
        else:
            print("  ❌ G2PWModel 下载失败（中文合成必需）")
            ok = False
    else:
        print("  已存在: text/G2PWModel")

    lid = os.path.join(pm, "fast_langdetect", "lid.176.bin")
    if not os.path.exists(lid) or args.force:
        print("== 语种检测模型 lid.176.bin（约 130MB）==")
        if not download_any([FASTTEXT_URL], lid):
            print("  ⚠️ 下载失败：中文合成可能报错（LangSegmenter 需要它）")
            ok = False
    else:
        print("  已存在: fast_langdetect/lid.176.bin")

    nltk = os.path.join(repo, "nltk_data")
    if not os.path.isdir(nltk) or args.force:
        print("== nltk_data（英文 G2P 备用，约 10MB）==")
        z = "/tmp/_nltk_data.zip"
        if download_any(["%s/%s/resolve/main/nltk_data.zip" % (m, EXTRA_REPO) for m in mirrors], z):
            with zipfile.ZipFile(z) as zf:
                zf.extractall(repo)
            os.remove(z)
        else:
            print("  ⚠️ 跳过（只影响英文参考音）")

    print("\n== 完成 ==" if ok else "\n== 部分文件下载失败，请看上面日志 ==")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
