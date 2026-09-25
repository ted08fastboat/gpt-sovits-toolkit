"""jieba_fast 兼容层（纯 Python）。

Windows 上 `pip install jieba_fast` 需要 Visual C++ 编译环境，多数人装不上，
而 GPT-SoVITS 的 text/chinese2.py、text/tone_sandhi.py 又会 `import jieba_fast`。
这里用纯 Python 的 jieba 顶替，接口保持一致（lcut / cut / posseg / setLogLevel）。
安装器会把本目录复制到 GPT-SoVITS 源码根目录，因此 `import jieba_fast` 优先命中它。
"""
import logging

import jieba as _jieba
from jieba import *  # noqa: F401,F403
from jieba import __version__, cut, cut_for_search, del_word, enable_parallel, initialize, lcut, load_userdict, posseg, suggest_freq, tokenize  # noqa: F401

# jieba_fast 特有的接口，jieba 没有，这里补上
DEFAULT_LOG_LEVEL = logging.INFO


def setLogLevel(level=DEFAULT_LOG_LEVEL):
    """jieba_fast.setLogLevel，jieba 本身没有这个方法。"""
    try:
        logging.getLogger("jieba").setLevel(level)
    except Exception:
        pass


def lcut_for_search(sentence, HMM=True):
    return _jieba.lcut_for_search(sentence, HMM=HMM)
