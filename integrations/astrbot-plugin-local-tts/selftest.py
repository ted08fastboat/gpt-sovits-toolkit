#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线自测：实例化插件，跑一遍 _synthesize，确认 HTTP 往返与落盘都正常。"""
import asyncio
import os
import sys
import tempfile

PLUGIN_DIR = "/vol1/@appdata/astrbot/data/plugins/astrbot_plugin_local_tts"
sys.path.insert(0, PLUGIN_DIR)
os.chdir(tempfile.mkdtemp(prefix="tts_selftest_"))

import main as plugin  # noqa: E402


class DummyContext:  # 插件只把 context 存起来，自测用空壳即可
    pass


CFG = {
    "base_url": "http://127.0.0.1:8001",
    "voice": "示例·晓晓",
    "speed": 1.0,
    "audio_format": "mp3",
    "timeout": 90,
    "max_chars": 300,
    "enable_tool": True,
    "enable_command": True,
    "text_fallback": True,
}


async def run():
    p = plugin.LocalTTSPlugin(DummyContext(), CFG)
    print("data_dir =", p.data_dir)
    print("base_url =", p._base_url())

    path, meta = await p._synthesize("这是插件自测，确认能从本机拿到语音。")
    print("短句 -> 文件 %s %d 字节" % (path.name, os.path.getsize(path)))
    print("        元信息", meta)

    voices, default = await p._voices()
    print("音色数 =", len(voices), "默认 =", default)

    long_text = "今天的天气很好，适合出去散步。我们下午三点在公园门口见面吧。" * 4
    path2, meta2 = await p._synthesize(long_text)
    print("长句 -> 截断=%s 实际字数=%d 耗时=%ss" % (meta2["truncated"], meta2["chars"], meta2["elapsed"]))


asyncio.run(run())
print("自测通过")
