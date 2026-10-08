"""日志：后台出的事有地方查，而且查得到的东西里没有 Key。"""

import argparse
import logging

import pytest

from wealthpilot import cli
from wealthpilot.services import logs


@pytest.fixture(autouse=True)
def _clean_log():
    assert "wealthpilot-test-" in str(logs.LOG_FILE)       # 写的是测试用的临时目录
    logs.setup()
    for handler in logging.getLogger("wealthpilot").handlers:
        handler.flush()
    logs.LOG_FILE.write_text("", encoding="utf-8")
    yield


def _logs(**kw):
    out: list[str] = []
    args = argparse.Namespace(**{**dict(lines=40, errors=False, follow=False, path=False), **kw})
    return cli.cmd_logs(args, out=out.append), "\n".join(out)


def test_what_went_wrong_in_the_background_can_be_read_back():
    log = logging.getLogger("wealthpilot.run")
    log.info("研究结束 状态=passed 用时=41秒 token=152000 类型=stock_deep 问题=%s", logs.brief("帮我深度分析一下宁德时代，重点看估值和资金流向，越细越好，谢谢"))
    try:
        raise RuntimeError("push failed")
    except RuntimeError:
        logging.getLogger("wealthpilot.channel").exception("feishu 里处理消息出错")
    code, text = _logs()
    assert code == 0 and "研究结束 状态=passed" in text and "宁德时代" in text and "谢谢" not in text       # 提问只记开头一小段
    assert "RuntimeError: push failed" in text                                                            # 出错的调用栈跟在那一条后面
    code, text = _logs(errors=True)
    assert "feishu 里处理消息出错" in text and "研究结束" not in text
    assert logs.recent_problems(24) == 1 and len(logs.tail(1)) == 1
    assert _logs(path=True)[1] == str(logs.LOG_FILE)


def test_keys_never_reach_the_log_file():
    log = logging.getLogger("wealthpilot.model")
    log.warning("调用失败：Incorrect API key provided: sk-abcdef1234567890abcdef. Authorization: Bearer abcdefgh12345678")
    log.warning("Telegram 收消息出错：%s", "https://api.telegram.org/bot1234567890:AAExampleExampleExampleExample00/getUpdates")
    text = logs.LOG_FILE.read_text(encoding="utf-8")
    assert "abcdef1234567890" not in text and "abcdefgh12345678" not in text and "AAExample" not in text
    assert "sk-…" in text and "调用失败" in text


def test_empty_log_says_so_and_follow_picks_up_new_lines(monkeypatch, tmp_path):
    assert "没有警告和错误" in _logs(errors=True)[1]
    stream = logs.follow(poll=0, rounds=2)
    logging.getLogger("wealthpilot.watch").warning("每日盯盘这一次出错了")
    assert any("每日盯盘这一次出错了" in line for line in stream)
    monkeypatch.setattr(logs, "LOG_FILE", tmp_path / "nothing.log")       # 从没运行过：文件还不存在
    assert "还没有日志" in _logs()[1] and logs.tail(5) == [] and logs.recent_problems() == 0


async def test_a_research_leaves_one_line_and_a_crash_leaves_a_traceback(monkeypatch):
    from tests.test_pipeline import PLAN, FakeClient, _done, _run
    from wealthpilot.services import runs

    def on_stream(kwargs):
        raise ValueError("bad request: context too long")
    done = _done(await _run(monkeypatch, FakeClient(on_stream, creates=[PLAN])))
    text = "\n".join(logs.tail(20))
    assert f"研究结束 状态={done['meta']['status']}" in text and "110011" in text

    async def explode():
        raise RuntimeError("boom")
        yield {}
    run = runs.Run(0, "问题", "conv-test")
    await runs._drive(run, explode())
    assert "研究执行异常" in "\n".join(logs.tail(5, errors=True)) and "RuntimeError: boom" in "\n".join(logs.tail(5, errors=True))
