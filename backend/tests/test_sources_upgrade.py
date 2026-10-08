"""技能来源（现成的、链接导入、AI 起草）与升级、自检。"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from wealthpilot import __version__
from wealthpilot.main import app
from wealthpilot.services import doctor, skills, upgrade

GOOD = (skills.GALLERY / "bank-check.md").read_text(encoding="utf-8")


def test_gallery_lists_and_installs():
    client = TestClient(app)
    items = client.get("/api/skills/gallery").json()
    assert len(items) >= 6 and all(i["label"] and i["description"] for i in items)
    assert not any(i["installed"] for i in items if i["name"] == "bank-check")
    assert client.post("/api/skills/gallery/bank-check/install").json()["name"] == "bank-check"
    assert next(i for i in client.get("/api/skills/gallery").json() if i["name"] == "bank-check")["installed"]
    assert skills.get("bank-check") is not None
    assert client.post("/api/skills/gallery/no-such/install").status_code == 404
    assert client.post("/api/skills/gallery/..%2Fsecret/install").status_code in (404, 405)
    skills.delete("bank-check")


def test_every_gallery_skill_is_valid():
    for file in skills.GALLERY.glob("*.md"):
        skill, problems = skills.parse(file.read_text(encoding="utf-8"), str(file))
        assert skill is not None and not problems, (file.name, problems)
        assert skill.name == file.stem


def test_raw_url():
    assert skills.raw_url("https://github.com/a/b/blob/main/skills/x.md") == "https://raw.githubusercontent.com/a/b/main/skills/x.md"
    assert skills.raw_url(" https://example.com/x.md ") == "https://example.com/x.md"


def _serve(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(skills.httpx if hasattr(skills, "httpx") else httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))


def test_import_previews_without_saving(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(200, text=GOOD))
    client = TestClient(app)
    r = client.post("/api/skills/import", json={"url": "https://github.com/a/b/blob/main/bank-check.md"})
    assert r.status_code == 200 and r.json()["skill"]["name"] == "bank-check" and r.json()["problems"] == []
    assert skills.get("bank-check") is None            # 只取回，不落盘


@pytest.mark.parametrize("url,handler,expect", [
    ("http://example.com/x.md", lambda r: httpx.Response(200, text=GOOD), "https"),
    ("file:///etc/passwd", lambda r: httpx.Response(200, text=GOOD), "https"),
    ("https://example.com/x.md", lambda r: httpx.Response(404), "404"),
    ("https://example.com/x.md", lambda r: httpx.Response(200, content=b"x" * (skills.MAX_REMOTE_BYTES + 1)), "太大"),
    ("https://example.com/x.md", lambda r: httpx.Response(200, content=b"\xff\xfe\x00bin"), "文本"),
])
def test_import_rejects(monkeypatch, url, handler, expect):
    _serve(monkeypatch, handler)
    r = TestClient(app).post("/api/skills/import", json={"url": url})
    assert r.status_code == 422 and expect in r.json()["detail"]


def test_import_reports_problems_of_a_bad_file(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(200, text="# 只是一篇文章\n没有 frontmatter"))
    body = TestClient(app).post("/api/skills/import", json={"url": "https://example.com/x.md"}).json()
    assert body["skill"] is None and body["problems"]


class _Model:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(text=self.replies.pop(0))


def test_draft_validates_and_retries_once():
    model = _Model("这是一个方法，没有格式", "```markdown\n" + GOOD + "```")
    content, problems = skills.draft(model, "m", "看银行股：息差、不良、拨备")
    assert problems == [] and content.startswith("---") and "```" not in content
    assert len(model.calls) == 2 and "这些问题" in model.calls[1]["messages"][-1]["content"]
    assert "fundamental" in model.calls[0]["system"] and "read_latest_report" in model.calls[0]["system"]
    # 两次都不合格：把草稿和问题一起还给用户，不假装成功
    content, problems = skills.draft(_Model("不行", "还是不行"), "m", "随便写一个")
    assert problems and content.strip() == "还是不行"


def test_draft_route_needs_a_model_and_a_description():
    client = TestClient(app)
    assert client.post("/api/skills/draft", json={"description": "短"}).status_code == 422
    assert client.post("/api/skills/draft", json={"description": "看银行股：息差、不良、拨备覆盖率"}).status_code == 409   # 测试环境没配 Key


# ── 升级 ────────────────────────────────────────────────

CHANGELOG = """# 更新记录

## 9.9.0 — 2026-11-01

- 新功能甲
- 新功能乙

## 0.2.0 — 2026-10-06

- 这一版

## 0.1.0 — 2026-10-05

- 更早
"""


def test_release_notes_only_newer_versions():
    notes = upgrade.release_notes(CHANGELOG, "0.2.0")
    assert [n["version"] for n in notes] == ["9.9.0"] and notes[0]["items"] == ["新功能甲", "新功能乙"] and notes[0]["date"] == "2026-11-01"
    assert [n["version"] for n in upgrade.release_notes(CHANGELOG)] == ["9.9.0", "0.2.0", "0.1.0"]
    assert upgrade.release_notes("没有版本标题") == []


def test_repo_changelog_covers_the_current_version():
    notes = upgrade.release_notes((upgrade.REPO / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert notes[0]["version"] == __version__ and notes[0]["items"]


def _fake_git(monkeypatch, answers: dict, calls: list | None = None):
    def git(*args, timeout=20):
        if calls is not None:
            calls.append(args)
        for key, value in answers.items():
            if args[:len(key)] == key:
                return value
        return 0, ""
    monkeypatch.setattr(upgrade, "_git", git)
    monkeypatch.setattr(upgrade, "is_checkout", lambda: True)


def test_check_reports_behind_and_caches(monkeypatch):
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc1234"), ("rev-parse", "--abbrev-ref"): (0, "main"),
                            ("status",): (0, ""), ("rev-list",): (0, "3"), ("show",): (0, CHANGELOG)}, calls)
    status = upgrade.check(force=True)
    assert status["behind"] == 3 and status["latest_version"] == "9.9.0" and "wealthpilot update" in status["how"]
    assert "9.9.0" in upgrade.notice()
    calls.clear()
    assert upgrade.check()["cached"] and not any(c[0] == "fetch" for c in calls)      # 第二次读缓存，不再联网
    assert upgrade.status()["behind"] == 3 and not any(c[0] == "fetch" for c in calls)  # 页面用的接口从不联网
    # 升完级（提交变了）：旧的缓存不再算数
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "def5678"), ("rev-parse", "--abbrev-ref"): (0, "main"),
                            ("status",): (0, ""), ("rev-list",): (0, "0"), ("show",): (0, CHANGELOG)})
    assert upgrade.notice() == ""
    assert upgrade.check()["behind"] == 0


def test_dirty_files_keep_their_first_letter(monkeypatch):
    # git status --porcelain 的行以状态列开头（可能是空格）；去掉行首空白会吃掉文件名的第一个字
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc1234"), ("rev-parse", "--abbrev-ref"): (0, "main"),
                            ("status",): (0, " M workbench/src/App.tsx\nM  backend/x.py")})
    assert upgrade.current()["dirty"] == ["workbench/src/App.tsx", "backend/x.py"]


def test_status_never_touches_the_network(monkeypatch):
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "fresh01"), ("rev-parse", "--abbrev-ref"): (0, "main"), ("status",): (0, "")}, calls)
    status = upgrade.status()
    assert status["checked"] is False and status["version"] == __version__ and not any(c[0] == "fetch" for c in calls)


def test_check_does_not_crash_when_git_cannot_compare(monkeypatch):
    """只跟踪一个分支的浅克隆里比不出来时，git 返回的是一段报错文字，不是数字。"""
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc1234"), ("rev-parse", "--abbrev-ref"): (0, "main"), ("status",): (0, ""),
                            ("rev-list",): (128, "fatal: ambiguous argument 'HEAD..FETCH_HEAD': unknown revision")}, calls)
    status = upgrade.check(force=True)
    assert status["checked"] is False and status["behind"] == 0 and "安装脚本" in status["how"]
    assert any(c[:2] == ("rev-list", "--count") and c[-1] == "HEAD..FETCH_HEAD" for c in calls)      # 不依赖 origin/main 这个引用


def test_check_survives_no_network_and_no_git(monkeypatch):
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "aaa0001"), ("rev-parse", "--abbrev-ref"): (0, "main"), ("fetch",): (1, "TimeoutExpired")})
    status = upgrade.check(force=True)
    assert status["checked"] is False and status["behind"] == 0 and "没能连上" in status["how"]
    # 不在 main 上：和 main 差多少没有意义，不联网、不比较
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "aaa0001"), ("rev-parse", "--abbrev-ref"): (0, "feat/x")}, calls)
    status = upgrade.check(force=True)
    assert status["checked"] is False and "feat/x" in status["how"] and not any(c[0] == "fetch" for c in calls)
    monkeypatch.setattr(upgrade, "is_checkout", lambda: False)
    assert "docker compose" in upgrade.check(force=True)["how"]


def test_update_refuses_to_touch_local_changes(monkeypatch):
    said: list[str] = []
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc1234"), ("rev-parse", "--abbrev-ref"): (0, "main"),
                            ("status",): (0, " M backend/src/x.py")}, calls)
    assert upgrade.update(said.append) is False
    assert any("没提交的改动" in s for s in said) and not any(c[0] == "pull" for c in calls)
    said.clear()
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc1234"), ("rev-parse", "--abbrev-ref"): (0, "feat/x"), ("status",): (0, "")}, calls)
    assert upgrade.update(said.append) is False and "feat/x" in said[0]


def test_update_already_latest_does_nothing(monkeypatch):
    said: list[str] = []
    calls: list = []
    _fake_git(monkeypatch, {("rev-parse", "--short"): (0, "abc9999"), ("rev-parse", "--abbrev-ref"): (0, "main"),
                            ("status",): (0, ""), ("rev-list",): (0, "0"), ("show",): (0, CHANGELOG)}, calls)
    assert upgrade.update(said.append) is True
    assert any("已经是最新" in s for s in said) and not any(c[0] == "pull" for c in calls)


def test_backup_keeps_only_recent(tmp_path, monkeypatch):
    db = tmp_path / "wealthpilot.db"
    db.write_bytes(b"data")
    monkeypatch.setattr(upgrade, "get_settings", lambda: SimpleNamespace(db_path=db))
    monkeypatch.setattr(upgrade, "KEEP_BACKUPS", 2)
    folder = tmp_path / "backups"
    folder.mkdir()
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (folder / f"wealthpilot-v0.1.0-{stamp}.db").write_bytes(b"old")
    saved = upgrade.backup_db()
    assert saved.read_bytes() == b"data"
    assert len(list(folder.glob("*.db"))) == 2 and saved in folder.glob("*.db")


# ── 自检 ────────────────────────────────────────────────

def test_doctor_says_what_is_wrong_and_how_to_fix(monkeypatch):
    async def sources():
        return [doctor._item("行情（新浪）", "ok", "0.2 秒"), doctor._item("公告（东方财富）", "fail", "取不到数据", "影响：公告。")]
    monkeypatch.setattr(doctor, "_sources", sources)
    monkeypatch.setattr(upgrade, "check", lambda **kw: {"checked": True, "behind": 2, "commit": "abc"})
    items = asyncio.run(doctor.run(online=False, port=59999))
    by_name = {i["name"]: i for i in items}
    assert by_name["模型"]["status"] == "fail" and "设置" in by_name["模型"]["fix"]          # 测试环境没有 Key
    assert by_name["数据库"]["status"] == "ok" and by_name["审计日志"]["status"] == "ok"
    assert by_name["端口 59999"]["detail"].startswith("空闲")
    assert by_name["手机触达"]["status"] == "warn"
    assert by_name["版本"]["status"] == "warn" and "wealthpilot update" in by_name["版本"]["fix"]
    text = doctor.render(items)
    assert "✗ 模型" in text and "→" in text and "项不通" in text


def test_doctor_keeps_going_when_one_check_itself_breaks(monkeypatch):
    async def sources():
        return [doctor._item("行情（新浪）", "ok", "0.2 秒")]

    def broken(**kw):
        raise ValueError("invalid literal for int()")
    monkeypatch.setattr(doctor, "_sources", sources)
    monkeypatch.setattr(upgrade, "check", broken)
    items = asyncio.run(doctor.run(online=False, port=59999))
    by_name = {i["name"]: i for i in items}
    assert by_name["版本与研究方法"]["status"] == "warn" and "没查成" in by_name["版本与研究方法"]["detail"]
    assert by_name["行情（新浪）"]["status"] == "ok" and "数据库" in by_name and "手机触达" in by_name      # 其余照常


def test_version_and_doctor_routes(monkeypatch):
    async def sources():
        return []
    monkeypatch.setattr(doctor, "_sources", sources)
    monkeypatch.setattr(upgrade, "check", lambda **kw: {**upgrade.current(), "checked": True, "behind": 0, "notes": []})
    client = TestClient(app)
    assert client.get("/api/settings/version").json()["version"] == __version__
    items = client.get("/api/settings/doctor").json()["items"]
    names = [i["name"] for i in items]
    assert "模型" in names and "数据库" in names
    # 从运行中的服务里自检：不该把自己的端口报成“空闲”
    assert next(i for i in items if i["name"].startswith("端口"))["detail"] == "WealthPilot 正在运行"
