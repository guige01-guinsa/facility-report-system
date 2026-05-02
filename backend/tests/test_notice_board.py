import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import notice_board
from app.main import app


class NoticeBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = notice_board.DB_PATH
        self.original_upload_dir = notice_board.UPLOAD_DIR
        notice_board.DB_PATH = Path(self.temp_dir.name) / "notice-board.db"
        notice_board.UPLOAD_DIR = Path(self.temp_dir.name) / "uploads"
        notice_board.init_notice_db()
        self.client = TestClient(app)

    def tearDown(self):
        notice_board.DB_PATH = self.original_db_path
        notice_board.UPLOAD_DIR = self.original_upload_dir
        self.temp_dir.cleanup()

    def test_notice_crud_and_remove_flow(self):
        created = self.client.post(
            "/api/notices",
            data={
                "category": "announcement",
                "title": "승강기 점검 안내",
                "description": "101동 승강기 정기 점검",
                "location": "101동",
                "line": "1-2라인",
                "floor": "1층",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
                "removal_due_date": "2026-05-11",
                "status": "posted",
            },
        )
        self.assertEqual(created.status_code, 200)
        notice_id = created.json()["id"]
        self.assertEqual(created.json()["category_label"], "공고문")
        self.assertEqual(created.json()["line"], "1-2라인")
        self.assertEqual(created.json()["floor"], "1층")

        listing = self.client.get("/api/notices", params={"q": "승강기"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["title"] for row in listing.json()], ["승강기 점검 안내"])

        updated = self.client.patch(
            f"/api/notices/{notice_id}",
            json={
                "category": "notice",
                "title": "승강기 점검 안내 수정",
                "location": "101동",
                "line": "3-4라인",
                "floor": "B1",
                "start_date": "2026-05-01",
                "end_date": "2026-05-12",
                "removal_due_date": "2026-05-13",
                "status": "posted",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "승강기 점검 안내 수정")

        removed = self.client.post(f"/api/notices/{notice_id}/remove", data={"removal_note": "철거 완료"})
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["computed_status"], "removed")

        deleted = self.client.delete(f"/api/notices/{notice_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])

    def test_rejects_invalid_period(self):
        response = self.client.post(
            "/api/notices",
            data={
                "category": "notice",
                "title": "기간 오류",
                "location": "관리동",
                "line": "1라인",
                "start_date": "2026-05-10",
                "end_date": "2026-05-01",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_init_db_adds_line_and_floor_to_existing_table(self):
        with notice_board.connect() as con:
            con.execute("DROP TABLE board_posts")
            con.execute(
                """
                CREATE TABLE board_posts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  category TEXT NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT,
                  location TEXT NOT NULL,
                  board_name TEXT,
                  start_date TEXT NOT NULL,
                  end_date TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'posted',
                  created_at TEXT NOT NULL DEFAULT (datetime('now')),
                  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            con.execute(
                """
                INSERT INTO board_posts(category, title, location, board_name, start_date, end_date)
                VALUES ('notice', '기존 게시물', '101동', '2층', '2026-05-01', '2026-05-10')
                """
            )

        notice_board.init_notice_db()

        with notice_board.connect() as con:
            columns = notice_board.table_columns(con, "board_posts")
            row = con.execute("SELECT line, floor FROM board_posts WHERE title = '기존 게시물'").fetchone()

        self.assertIn("line", columns)
        self.assertIn("floor", columns)
        self.assertEqual(row["floor"], "2층")


if __name__ == "__main__":
    unittest.main()
