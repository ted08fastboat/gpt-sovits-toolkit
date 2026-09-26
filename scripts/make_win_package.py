#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装 Windows 轻量安装包到桌面，并用 Python zipfile 打包（保证 UTF-8 文件名标志，
避免 Windows 解压后中文名乱码）。"""
import os
import shutil
import zipfile

HOME = os.path.expanduser("~")
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(WS, "win")
ENV = os.path.join(HOME, "GPT-SoVITS")
NAME = "GPT-SoVITS-Windows-轻量安装包"
PKG = os.path.join(HOME, "Desktop", NAME)
ZIP = os.path.join(HOME, "Desktop", NAME + ".zip")

# 1. 清空并重建
if os.path.exists(PKG):
    shutil.rmtree(PKG)
os.makedirs(PKG)

def cp(src, dst=None):
    dst = dst or os.path.join(PKG, os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

# 2. 脚本与说明
for f in ("安装.bat", "install.py", "clone_win.py", "使用说明.txt"):
    cp(os.path.join(SRC, f))
cp(os.path.join(SRC, "jieba_fast"))
# ASCII 别名的安装入口（防止解压后中文名异常时仍可用）
shutil.copy2(os.path.join(SRC, "安装.bat"), os.path.join(PKG, "install.bat"))
# 合成引擎（带音量归一化的最新版）
cp(os.path.join(ENV, "tts_clone.py"))

# 网页界面「声音工坊」（安装后可用 启动声音工坊.bat 打开）
ui_src = os.path.join(WS, "ui", "app")
ui_dst = os.path.join(PKG, "ui")
os.makedirs(ui_dst, exist_ok=True)
for rel in ("main.py", "synth.py"):
    shutil.copy2(os.path.join(ui_src, rel), os.path.join(ui_dst, rel))
os.makedirs(os.path.join(ui_dst, "static"), exist_ok=True)
shutil.copy2(os.path.join(ui_src, "static", "index.html"),
             os.path.join(ui_dst, "static", "index.html"))
print("已加入网页界面文件: ui/")

# 3. 权重（示例音色 v2Pro）
os.makedirs(os.path.join(PKG, "权重"), exist_ok=True)
for f, d in (("model.ckpt", os.path.join(ENV, "GPT_weights_v2Pro")),
             ("model.pth", os.path.join(ENV, "SoVITS_weights_v2Pro"))):
    cp(os.path.join(d, f), os.path.join(PKG, "权重", f))

# 4. 参考音频（默认男声 Rocko，附备用）+ 台词示例
REF = os.path.join(PKG, "参考音频")
os.makedirs(os.path.join(REF, "备用"), exist_ok=True)
# 参考音色优先取安装目录（清理工作区后 test/ 可能已删除）
V = os.path.join(os.path.expanduser("~"), "GPT-SoVITS", "参考音频", "备用")
if not os.path.isdir(V):
    V = os.path.join(WS, "test", "voices")
VOICE_MAP = {"男声-Rocko.wav": "Rocko_中文_中国大陆.wav",
             "男声-Reed.wav": "Reed_中文_中国大陆.wav",
             "女声-婷婷.wav": "Tingting_中文_中国大陆.wav"}
src_rocko = os.path.join(V, VOICE_MAP["男声-Rocko.wav"])
if not os.path.exists(src_rocko):
    src_rocko = os.path.join(V, "男声-Rocko.wav")
shutil.copy2(src_rocko, os.path.join(REF, "ref.wav"))
with open(os.path.join(REF, "ref.txt"), "w", encoding="utf-8") as f:
    f.write("各位听众朋友大家好，欢迎收听今天的科技新闻节目。")
_src = os.path.join(V, "Tingting_中文_中国大陆.wav")
if not os.path.exists(_src):
    _src = os.path.join(V, "女声-婷婷.wav")
shutil.copy2(_src, os.path.join(REF, "备用", "女声-婷婷.wav"))
with open(os.path.join(REF, "备用", "女声-婷婷.txt"), "w", encoding="utf-8") as f:
    f.write("各位听众朋友大家好，欢迎收听今天的科技新闻节目。")
_src = os.path.join(V, "Reed_中文_中国大陆.wav")
if not os.path.exists(_src):
    _src = os.path.join(V, "男声-Reed.wav")
shutil.copy2(_src, os.path.join(REF, "备用", "男声-Reed.wav"))
with open(os.path.join(REF, "备用", "男声-Reed.txt"), "w", encoding="utf-8") as f:
    f.write("各位听众朋友大家好，欢迎收听今天的科技新闻节目。")
with open(os.path.join(REF, "说明.txt"), "w", encoding="utf-8") as f:
    f.write(
        "参考音频放这里（当前默认：男声 Rocko，中位基频约 112Hz）\n"
        "  ref.wav  3~10 秒干净人声（wav/mp3/m4a 均可）\n"
        "  ref.txt  这段音频的逐字文字\n\n"
        "想换成自己的声音：替换这两个文件即可。\n"
        "想切回女声或换别的男声：「备用」文件夹里有现成的 wav + txt，\n"
        "复制出来改名为 ref.wav / ref.txt 即可。\n"
    )
with open(os.path.join(PKG, "台词.txt"), "w", encoding="utf-8") as f:
    f.write("# 一行一句，以 # 开头忽略（批量克隆用）\n这是第一句测试台词。\n这是第二句测试台词。\n")

# 5. 打包
total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(PKG) for f in fs)
print("包内容总大小: %.1f MB" % (total / 1024 / 1024))
if os.path.exists(ZIP):
    os.remove(ZIP)
print("压缩中（Python zipfile，UTF-8 文件名标志）…")
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
    for root, _, files in os.walk(PKG):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, os.path.dirname(PKG)))

# 6. 校验 UTF-8 标志位
with zipfile.ZipFile(ZIP) as z:
    nonascii = [i for i in z.infolist() if any(ord(c) > 127 for c in i.filename)]
    flagged = [i for i in nonascii if i.flag_bits & 0x800]
    print("非 ASCII 文件名: %d 个，其中带 UTF-8 标志: %d 个" % (len(nonascii), len(flagged)))
    for i in nonascii[:6]:
        print("   %-40s utf8=%s" % (i.filename, bool(i.flag_bits & 0x800)))
print("zip 大小: %.1f MB -> %s" % (os.path.getsize(ZIP) / 1024 / 1024, ZIP))
