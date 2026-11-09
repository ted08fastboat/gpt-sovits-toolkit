# -*- coding: utf-8 -*-
"""本地语音（GPT-SoVITS）

把文字交给本机 8001 端口的「声音工坊」服务合成语音，然后作为语音消息发出去。

对模型的接口是一个 LLM 工具 say_aloud：模型可以自己判断该不该发语音；
另外提供 /说、/音色 两个指令给用户手动用。

服务端协议用的是 OpenAI TTS 兼容接口：
    POST {base_url}/v1/audio/speech
    {"model": "tts-1", "input": "...", "voice": "...", "response_format": "mp3"}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import AsyncIterator

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Record
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.message.message_event_result import MessageChain

PLUGIN_NAME = "astrbot_plugin_local_tts"
KEEP_FILES = 80  # 本地缓存保留的音频数量


class LocalTTSPlugin(Star):
    """让模型从本机语音服务拿音频并发送。"""

    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config
        try:
            self.data_dir: Path = StarTools.get_data_dir(PLUGIN_NAME)
        except Exception:  # noqa: BLE001
            self.data_dir = Path("data/plugin_data") / PLUGIN_NAME
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 配置
    def _conf(self, key: str, default=None):
        cfg = self.config
        if cfg is None:
            return default
        try:
            val = cfg.get(key, default)
        except Exception:  # noqa: BLE001
            val = getattr(cfg, key, default)
        if val is None or (isinstance(val, str) and not val.strip()):
            return default
        return val

    def _base_url(self) -> str:
        return str(self._conf("base_url", "http://127.0.0.1:8001")).rstrip("/")

    def _timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=int(self._conf("timeout", 90)))

    # ------------------------------------------------------------ 合成
    async def _synthesize(self, text: str, voice: str = "", speed: float = 0.0):
        text = (text or "").strip()
        if not text:
            raise ValueError("要念的文字是空的")

        limit = int(self._conf("max_chars", 80))
        truncated = len(text) > limit
        if truncated:
            head = text[:limit]
            cut = max(head.rfind(p) for p in "。！？；!?;\n，,")
            text = head[: cut + 1] if cut > limit * 0.5 else head

        fmt = str(self._conf("audio_format", "mp3")).lower()
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": (voice or "").strip() or str(self._conf("voice", "") or ""),
            "response_format": fmt,
        }
        sp = float(speed or 0) or float(self._conf("speed", 1.0) or 1.0)
        if abs(sp - 1.0) > 1e-3:
            payload["speed"] = sp

        url = self._base_url() + "/v1/audio/speech"
        t0 = time.time()
        async with aiohttp.ClientSession(timeout=self._timeout()) as sess:
            async with sess.post(url, json=payload) as resp:
                body = await resp.read()
                if resp.status != 200:
                    detail = body.decode("utf-8", "ignore").strip()[:200]
                    raise RuntimeError(f"服务返回 {resp.status}：{detail or '无内容'}")
        if not body:
            raise RuntimeError("服务返回了空音频")

        ext = {"mp3": "mp3", "wav": "wav", "opus": "ogg", "ogg": "ogg"}.get(fmt, "mp3")
        out = Path(self.data_dir) / f"tts_{int(time.time() * 1000)}.{ext}"
        out.write_bytes(body)
        self._cleanup()

        meta = {
            "voice": payload["voice"] or "(服务端默认)",
            "bytes": len(body),
            "elapsed": round(time.time() - t0, 1),
            "chars": len(text),
            "truncated": truncated,
        }
        logger.info("[local_tts] 合成完成 %s", meta)
        return out, meta

    def _cleanup(self) -> None:
        try:
            files = sorted(Path(self.data_dir).glob("tts_*"), key=lambda p: p.stat().st_mtime)
            for old in files[:-KEEP_FILES]:
                old.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    async def _voices(self):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            async with sess.get(self._base_url() + "/v1/voices") as resp:
                data = await resp.json()
        return data.get("voices", []), data.get("default")

    # ------------------------------------------------------------ LLM 工具
    @filter.llm_tool(name="say_aloud")
    async def say_aloud(
        self,
        event: AstrMessageEvent,
        text: str,
        voice: str = "",
        speed: float = 0,
    ) -> str:
        """把一段文字用本地语音模型念出来，作为语音消息发给用户。

        什么时候该用：用户说"念出来 / 发条语音 / 用语音说"，或者这条回复本身用声音表达更合适。
        什么时候不该用：代码、表格、链接清单、超过 80 字的长文本、纯符号内容（这台是 CPU 推理，字越多等越久）。
        调用之后只需要回一句很短的确认，不要重复原文，也不要再说一遍"我已经发送语音"之外的话。

        Args:
            text(string): 要念出来的文字，必须是口语化的完整句子，不要包含 Markdown 标记、代码块、网址或表情符号
            voice(string): 音色名，例如 晓晓、云希、晓伊；留空则使用插件配置的默认音色
            speed(number): 语速倍率，0.8 到 1.2 之间，填 0 表示使用默认语速
        """
        if not self._conf("enable_tool", True):
            return "语音工具已在插件配置中关闭，请直接用文字回复。"

        if not (text or "").strip():
            return "没有可朗读的文字。"

        try:
            path, meta = await self._synthesize(text, voice, speed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[local_tts] 合成失败：%s", exc)
            return f"语音合成失败（{exc}）。请改用文字回复用户。"

        try:
            await event.send(MessageChain([Record.fromFileSystem(str(path))]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[local_tts] 语音发送失败：%s", exc)
            if self._conf("text_fallback", True):
                return f"语音已合成但发送失败（{exc}），请直接把这段文字发给用户：{text}"
            return f"语音发送失败：{exc}"

        extra = "，原文超过长度上限已截断" if meta["truncated"] else ""
        return (
            f"已发送 {meta['bytes'] // 1024} KB 语音，音色 {meta['voice']}，"
            f"合成耗时 {meta['elapsed']} 秒{extra}。"
        )

    # ------------------------------------------------------------ 指令
    @filter.command("说")
    async def cmd_say(self, event: AstrMessageEvent, content: str = "") -> AsyncIterator[object]:
        """把后面的文字念成语音发出来，例如：/说 今天记得带伞"""
        if not self._conf("enable_command", True):
            yield event.plain_result("语音指令已在插件配置里关闭。")
            return

        text = (content or "").strip() or self._after_command(event, "说")
        if not text:
            yield event.plain_result("用法：/说 要念的文字")
            return

        try:
            path, meta = await self._synthesize(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[local_tts] 指令合成失败：%s", exc)
            yield event.plain_result(f"合成失败：{exc}")
            return

        yield event.chain_result([Record.fromFileSystem(str(path))])

    @filter.command("音色")
    async def cmd_voices(self, event: AstrMessageEvent) -> AsyncIterator[object]:
        """查看可用的音色列表"""
        try:
            voices, default = await self._voices()
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"取不到音色列表：{exc}")
            return
        if not voices:
            yield event.plain_result("服务里还没有任何音色。")
            return
        lines = ["可用音色："]
        for v in voices:
            vid = str(v.get("id", "")).replace(".wav", "")
            mark = "（默认）" if v.get("id") == default else ""
            dur = v.get("dur")
            tail = f"  {dur:.2f}s" if isinstance(dur, (int, float)) else ""
            lines.append(f"· {vid}{tail}{mark}")
        lines.append("用法：/说 文字，或在插件配置里改默认音色。")
        yield event.plain_result("\n".join(lines))

    # ------------------------------------------------------------ 工具方法
    @staticmethod
    def _after_command(event: AstrMessageEvent, cmd: str) -> str:
        raw = (event.message_str or "").strip()
        for prefix in ("/", "／", "#"):
            head = prefix + cmd
            if raw.startswith(head):
                return raw[len(head):].strip()
        if raw.startswith(cmd):
            return raw[len(cmd):].strip()
        return raw

    # ------------------------------------------------------------ 生命周期
    @filter.on_astrbot_loaded()
    async def _on_loaded(self):
        base = self._base_url()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
                async with sess.get(base + "/health") as resp:
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[local_tts] 连不上语音服务 %s：%s（用它之前先把它启动起来）", base, exc)
            return
        voices = data.get("voices") or []
        logger.info(
            "[local_tts] 语音服务已连通 %s｜就绪=%s｜可用音色 %d 个｜默认音色=%s",
            base, data.get("ready"), len(voices), self._conf("voice", "") or data.get("default_voice"),
        )
