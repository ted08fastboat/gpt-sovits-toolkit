# 本地语音（GPT-SoVITS）· AstrBot 插件

让 AstrBot 里的模型从**本机 8001 端口**的语音服务取音频并发出去。
模型通过 LLM 工具 `say_aloud` 自己决定要不要发语音；用户也可以用指令手动触发。

## 它依赖的服务

就是 NAS 上那个「声音工坊」容器（GPT-SoVITS），对外是 OpenAI TTS 兼容接口：

```
POST http://127.0.0.1:8001/v1/audio/speech
{"model":"tts-1","input":"要念的文字","voice":"示例·晓晓","response_format":"mp3"}
```

AstrBot 和它在同一台机器上，所以直接走 `127.0.0.1`，不经过网络、不上外网。

## 提供的三样东西

| 类型 | 名称 | 说明 |
|---|---|---|
| LLM 工具 | `say_aloud(text, voice?, speed?)` | 模型判断该发语音时自己调用；插件合成后直接发语音消息，并把结果回给模型 |
| 指令 | `/说 文字` | 手动把文字念出来，例如 `/说 今天记得带伞` |
| 指令 | `/音色` | 列出服务端可用的音色和默认音色 |

## 配置项（AstrBot 面板 → 插件管理 → 本地语音）

| 键 | 默认值 | 说明 |
|---|---|---|
| `base_url` | `http://127.0.0.1:8001` | 语音服务地址 |
| `voice` | `示例·晓晓` | 默认音色，支持简写（`晓晓` 也行） |
| `speed` | `1.0` | 默认语速 |
| `audio_format` | `mp3` | 音频格式 |
| `timeout` | `120` | 合成超时（秒），CPU 推理慢，别低于 60 |
| `max_chars` | `80` | 单次最长字数，超出按句末标点截断（约 0.6 秒/字） |
| `enable_tool` | `true` | 是否给模型开放 `say_aloud` |
| `enable_command` | `true` | 是否启用 `/说`、`/音色` |
| `text_fallback` | `true` | 发不出音频时改发文字 |

## 安装

插件目录：`/vol1/@appdata/astrbot/data/plugins/astrbot_plugin_local_tts/`

装完需要重启 AstrBot。启动日志里出现下面这行就说明配置正确：

```
[local_tts] 语音服务已连通 http://127.0.0.1:8001｜就绪=True｜可用音色 3 个｜默认音色=示例·晓晓
```

连不上会打 `warning`，不影响 AstrBot 其它功能。

## 备注

- 音频临时文件放在 `data/plugin_data/astrbot_plugin_local_tts/`，自动只保留最近 80 个。
- 语音消息的支持取决于消息平台：QQ（aiocqhttp）支持，部分平台会退化成文字（看 `text_fallback`）。
- 和 AstrBot 自带的「OpenAI TTS 提供商」不冲突：那个是每条回复都转语音，这个插件是让模型**按需**发语音。两个可以同时开着。
