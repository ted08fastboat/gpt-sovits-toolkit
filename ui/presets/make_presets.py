#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成内置示例音色的参考音频（presets/ 里只提交清单，音频靠这个脚本现生成）。

依赖：edge-tts（微软在线语音，纯 Python，Mozilla 语音库规模小）
    pip install edge-tts

用法：
    python make_presets.py            # 生成到本目录
    python make_presets.py --out DIR  # 生成到指定目录

生成结果要和 presets.json 里的 file 字段对上（xiaoxiao.mp3 / yunxi.mp3 / xiaoyi.mp3）。
"""
import argparse
import asyncio
import os
import sys

try:
    import edge_tts
except ImportError:
    sys.exit("缺少依赖：pip install edge-tts")

# 音色 → (输出文件名, 朗读内容)
JOBS = [
    ("zh-CN-XiaoxiaoNeural", "xiaoxiao.mp3", "今天的天气很好，适合出去散步。我们下午三点在公园门口见面吧。"),
    ("zh-CN-YunxiNeural", "yunxi.mp3", "这个功能已经做好了，你可以先试用一下，有问题随时告诉我。"),
    ("zh-CN-XiaoyiNeural", "xiaoyi.mp3", "我刚刚看完那本书，写得真不错，推荐你也读一读。"),
]


async def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for voice, name, text in JOBS:
        path = os.path.join(out_dir, name)
        await edge_tts.Communicate(text, voice, rate="-4%").save(path)
        print("生成 %-14s %6.1f KB  %s" % (name, os.path.getsize(path) / 1024, text[:16] + "…"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(main(ap.parse_args().out))
