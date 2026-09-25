#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 一键克隆 / 批量克隆（由 一键克隆.bat、批量克隆.bat 调用）。

自动从 GPT_weights_v2Pro / SoVITS_weights_v2Pro 找到音色权重，
用 参考音频\\ref.wav + ref.txt 作为参考，结果写到 输出音频\\。
"""
import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, "venv", "Scripts", "python.exe")
REF_DIR = os.path.join(HERE, "参考音频")
OUT_DIR = os.path.join(HERE, "输出音频")
ENGINE = os.path.join(HERE, "tts_clone.py")


def find_weight(kind):
    """kind: 'gpt' -> .ckpt, 'sovits' -> .pth"""
    if kind == "gpt":
        pats = [os.path.join(HERE, "GPT_weights_v2Pro", "*.ckpt"),
                os.path.join(HERE, "GPT_weights_v2", "*.ckpt"),
                os.path.join(HERE, "GPT_weights", "*.ckpt")]
    else:
        pats = [os.path.join(HERE, "SoVITS_weights_v2Pro", "*.pth"),
                os.path.join(HERE, "SoVITS_weights_v2", "*.pth"),
                os.path.join(HERE, "SoVITS_weights", "*.pth")]
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits[0]
    return None


def play(path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # noqa: S606
            return
        if sys.platform == "darwin":
            subprocess.run(["afplay", path], check=False)
    except Exception as e:  # noqa: BLE001
        print("（播放失败：%s，可手动打开文件）" % e)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    batch = "--batch" in sys.argv

    if not os.path.exists(VENV_PY):
        print("❌ 找不到 %s，请先运行「安装.bat」。" % VENV_PY)
        return 1
    gpt = find_weight("gpt")
    sovits = find_weight("sovits")
    if not gpt or not sovits:
        print("❌ 权重目录里没有 .ckpt / .pth，请先运行「安装.bat」。")
        return 1
    ref_wav = os.path.join(REF_DIR, "ref.wav")
    ref_txt = os.path.join(REF_DIR, "ref.txt")
    if not os.path.exists(ref_wav):
        # 允许 ref.mp3 / ref.m4a 等，交给引擎转码
        for ext in ("mp3", "m4a", "aiff", "flac"):
            cand = os.path.join(REF_DIR, "ref." + ext)
            if os.path.exists(cand):
                ref_wav = cand
                break
    if not (os.path.exists(ref_wav) and os.path.exists(ref_txt)):
        print("❌ 参考音频缺失：请把 ref.wav(3~10秒干净人声) 和 ref.txt 放到 %s" % REF_DIR)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    before = set(glob.glob(os.path.join(OUT_DIR, "*.wav")))

    env = dict(os.environ)
    env.update({
        "PATH": os.path.join(HERE, "venv", "Scripts") + os.pathsep + env.get("PATH", ""),
        "PYTHONPATH": HERE + os.pathsep + os.path.join(HERE, "GPT_SoVITS"),
        "HF_ENDPOINT": "https://hf-mirror.com",
        "NLTK_DATA": os.path.join(HERE, "nltk_data"),
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
        "language": "zh_CN",
        "version": "v2Pro",
        "gpt_path": gpt,
        "sovits_path": sovits,
    })

    if batch:
        lines = os.path.join(HERE, "台词.txt")
        if not os.path.exists(lines):
            with open(lines, "w", encoding="utf-8") as f:
                f.write("# 一行一句，以 # 开头忽略\n你好，这是第一句。\n这是第二句。\n")
            print("已生成示例台词文件：%s，请编辑后重新运行。" % lines)
            try:
                if hasattr(os, "startfile"):
                    os.startfile(lines)  # noqa: S606
            except Exception:  # noqa: BLE001
                pass
            return 0
        print("台词文件：%s" % lines)
        cmd = [VENV_PY, ENGINE, "--batch-file", lines, "--out-dir", OUT_DIR,
               "--ref-wav", ref_wav, "--ref-text-file", ref_txt,
               "--ref-lang", "中文", "--text-lang", "中文", "--prefix", "batch"]
    else:
        print("=" * 60)
        print(" GPT-SoVITS 一键克隆（当前音色）")
        print("=" * 60)
        print("参考音频：%s" % ref_wav)
        print("输出目录：%s" % OUT_DIR)
        print()
        text = input("请输入要合成的台词，回车开始：\n> ").strip()
        if not text:
            print("没有输入，退出。")
            return 1
        tmp = os.path.join(tempfile.gettempdir(), "gptsovits_line.txt")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        print("\n正在合成（CPU 推理，约 30~60 秒）…\n")
        cmd = [VENV_PY, ENGINE, "--text-file", tmp, "--out-dir", OUT_DIR,
               "--ref-wav", ref_wav, "--ref-text-file", ref_txt,
               "--ref-lang", "中文", "--text-lang", "中文", "--variants", "2",
               "--prefix", "line"]

    rc = subprocess.run(cmd, cwd=HERE, env=env).returncode
    new = sorted(set(glob.glob(os.path.join(OUT_DIR, "*.wav"))) - before,
                 key=os.path.getmtime, reverse=True)
    if new:
        print("\n✅ 完成 %d 个文件：" % len(new))
        for f in new:
            print("   " + os.path.basename(f))
        play(new[0])
    else:
        print("\n❌ 没有生成音频（退出码 %s），请把上面的输出发回排查。" % rc)
        return 1
    try:
        if hasattr(os, "startfile"):
            os.startfile(OUT_DIR)  # noqa: S606
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
