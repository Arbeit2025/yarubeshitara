"""やるべしたら Web版 yarubeshitara

Markdown のチェックリスト記法でタスクを読み書きできる手帳風タスク管理。
「- [ ] タスク」「- [x] 完了タスク」の貼り付け取り込みと、
全タスクの Markdown 書き出し（エクスポート）に対応する。
単一ファイル Flask + SQLite。
"""
import os
import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, Response, g, jsonify, redirect, render_template_string, request, url_for

app = Flask(__name__)
JST = ZoneInfo("Asia/Tokyo")
DB_PATH = os.environ.get("YARUBESHITARA_DB", os.path.join(os.path.dirname(__file__), "yarubeshitara.db"))

CHECK_RE = re.compile(r"^[-*]\s*\[( |x|X)\]\s*(.+)$")
BULLET_RE = re.compile(r"^[-*]\s+(.+)$")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()


def parse_markdown(text):
    """Markdownテキストを (text, done) のリストに変換する。

    - "- [ ] タスク" → 未完了、"- [x] タスク" → 完了
    - "- タスク" のような箇条書きや、ただの行もタスクとして取り込む
    - 空行は無視する
    """
    tasks = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        m = CHECK_RE.match(s)
        if m:
            tasks.append((m.group(2).strip(), 1 if m.group(1) in ("x", "X") else 0))
            continue
        m = BULLET_RE.match(s)
        if m:
            tasks.append((m.group(1).strip(), 0))
            continue
        tasks.append((s, 0))
    return [(t, d) for (t, d) in tasks if t]


def tasks_to_markdown(tasks):
    lines = []
    for t in tasks:
        lines.append(f"- [{'x' if t['done'] else ' '}] {t['text']}")
    return "\n".join(lines) + ("\n" if lines else "")


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>やるべしたら Web版</title>
<style>body{font-family:sans-serif;max-width:680px;margin:2em auto;padding:0 1em}
.done{text-decoration:line-through;color:#888}
textarea{width:100%}code{background:#f0f0f0;padding:.1em .3em}
li{margin:.4em 0}</style>
</head><body>
<h1>やるべしたら Web版</h1>
<p>Markdown で読み書きできる、手帳風のタスク管理です。</p>

<h2>タスク一覧</h2>
<ul style="list-style:none;padding-left:0">
{% for t in tasks %}
<li>
  <form method="post" action="{{ url_for('toggle', tid=t.id) }}" style="display:inline"><button type="submit">{{ '☑' if t.done else '☐' }}</button></form>
  <span class="{{ 'done' if t.done }}">{{ t.text }}</span>
  <small>（{{ t.created_at }}）</small>
  <form method="post" action="{{ url_for('delete', tid=t.id) }}" style="display:inline" onsubmit="return confirm('このタスクを削除しますか？')"><button type="submit">削除</button></form>
</li>
{% else %}<li>タスクはまだありません</li>{% endfor %}
</ul>
<p><a href="{{ url_for('export') }}">Markdownでエクスポート（ダウンロード）</a>：全タスクを <code>- [ ] タスク</code> 形式のテキストで書き出します。コピーして手帳やメモに貼れます。</p>

<h2>タスクを追加</h2>
<form method="post" action="{{ url_for('add') }}">
  <input type="text" name="text" placeholder="やること" required size="40">
  <button type="submit">追加</button>
</form>

<h2>Markdownから取り込む（インポート）</h2>
<p>下の欄に Markdown を貼り付けて「取り込む」を押すと、行ごとにタスクとして追加されます。<br>
<code>- [ ] 未完了のタスク</code>／<code>- [x] 完了したタスク</code>／ただの文章の行もそのままタスクになります。</p>
<form method="post" action="{{ url_for('import_md') }}">
  <textarea name="markdown" rows="6" placeholder="- [ ] 牛乳を買う&#10;- [x] 洗濯した&#10;明日の予定を書く"></textarea><br>
  <button type="submit">取り込む</button>
</form>
</body></html>"""


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()
    return render_template_string(PAGE, tasks=tasks)


@app.route("/add", methods=["POST"])
def add():
    text = (request.form.get("text") or "").strip()
    if text:
        db = get_db()
        db.execute(
            "INSERT INTO tasks(text, done, created_at) VALUES(?, 0, ?)",
            (text, datetime.now(JST).strftime("%Y-%m-%d")),
        )
        db.commit()
    return redirect(url_for("index"))


@app.route("/import", methods=["POST"])
def import_md():
    parsed = parse_markdown(request.form.get("markdown") or "")
    if parsed:
        db = get_db()
        today = datetime.now(JST).strftime("%Y-%m-%d")
        db.executemany(
            "INSERT INTO tasks(text, done, created_at) VALUES(?, ?, ?)",
            [(t, d, today) for (t, d) in parsed],
        )
        db.commit()
    return redirect(url_for("index"))


@app.route("/toggle/<int:tid>", methods=["POST"])
def toggle(tid):
    db = get_db()
    db.execute("UPDATE tasks SET done = 1 - done WHERE id = ?", (tid,))
    db.commit()
    return redirect(url_for("index"))


@app.route("/delete/<int:tid>", methods=["POST"])
def delete(tid):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (tid,))
    db.commit()
    return redirect(url_for("index"))


@app.route("/export")
def export():
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()
    return Response(
        tasks_to_markdown(tasks),
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=yarubeshitara.md"},
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
