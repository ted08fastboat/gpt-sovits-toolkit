"""jieba_fast.posseg 兼容层：直接转发到 jieba.posseg。"""
from jieba.posseg import *  # noqa: F401,F403
from jieba.posseg import POSTokenizer, dt, cut, initialize, lcut, pair  # noqa: F401
