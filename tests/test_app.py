import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["YARUBESHITARA_DB"] = _tmp.name

import app as app_module  # noqa: E402


class YarubeshitaraTest(unittest.TestCase):
    def setUp(self):
        app_module.init_db()
        self.client = app_module.app.test_client()
        with app_module.app.app_context():
            conn = app_module.get_db()
            conn.execute("DELETE FROM tasks")
            conn.commit()

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_index_ok(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("やるべしたら", body)
        self.assertIn("Markdown", body)

    def test_parse_markdown(self):
        parsed = app_module.parse_markdown("- [ ] 買い物\n- [x] 掃除\nただの行\n\n- 箇条書き")
        self.assertEqual(
            parsed,
            [("買い物", 0), ("掃除", 1), ("ただの行", 0), ("箇条書き", 0)],
        )

    def test_import_flow(self):
        res = self.client.post(
            "/import", data={"markdown": "- [ ] 買い物\n- [x] 掃除\nメモの行"}
        )
        self.assertEqual(res.status_code, 302)
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("買い物", body)
        self.assertIn("掃除", body)
        self.assertIn("メモの行", body)
        with app_module.app.app_context():
            conn = app_module.get_db()
            rows = conn.execute("SELECT text, done FROM tasks ORDER BY id").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["done"], 1)

    def test_export_format(self):
        self.client.post("/import", data={"markdown": "- [ ] 買い物\n- [x] 掃除"})
        res = self.client.get("/export")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.content_type)
        text = res.get_data(as_text=True)
        self.assertIn("- [ ] 買い物", text)
        self.assertIn("- [x] 掃除", text)

    def test_add_toggle_delete(self):
        self.client.post("/add", data={"text": "本を読む"})
        with app_module.app.app_context():
            conn = app_module.get_db()
            row = conn.execute("SELECT * FROM tasks").fetchone()
            tid = row["id"]
            self.assertEqual(row["done"], 0)
        self.client.post(f"/toggle/{tid}")
        with app_module.app.app_context():
            conn = app_module.get_db()
            self.assertEqual(
                conn.execute("SELECT done FROM tasks WHERE id=?", (tid,)).fetchone()["done"], 1
            )
        self.client.post(f"/delete/{tid}")
        with app_module.app.app_context():
            conn = app_module.get_db()
            self.assertIsNone(conn.execute("SELECT * FROM tasks").fetchone())


if __name__ == "__main__":
    unittest.main()
