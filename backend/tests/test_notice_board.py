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
        location = self.client.post(
            "/api/notices/locations",
            json={"building": "101동", "line": "1-2라인", "floor": "1층", "sort_order": 1},
        )
        self.assertEqual(location.status_code, 200)

        locations = self.client.get("/api/notices/locations")
        self.assertEqual(locations.status_code, 200)
        self.assertEqual(locations.json()["tree"]["101동"]["1-2라인"], ["1층"])

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

    def test_specific_location_option_and_notice_usage(self):
        option = self.client.post(
            "/api/notices/specific-locations",
            json={"name": "승강기 앞", "sort_order": 1},
        )
        self.assertEqual(option.status_code, 200)

        listed = self.client.get("/api/notices/specific-locations")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["name"], "승강기 앞")

        created = self.client.post(
            "/api/notices",
            data={
                "category": "notice",
                "title": "특정위치 테스트",
                "location": "101동",
                "line": "1라인",
                "floor": "1층",
                "specific_location": "승강기 앞",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["specific_location"], "승강기 앞")

    def test_notice_accepts_pdf_attachment(self):
        created = self.client.post(
            "/api/notices",
            data={
                "category": "notice",
                "title": "PDF 게시물",
                "location": "102동",
                "line": "1라인",
                "floor": "2층",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
            },
            files={"attachment": ("notice.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["attachment_filename"], "notice.pdf")
        self.assertEqual(body["attachment_content_type"], "application/pdf")
        self.assertTrue(body["attachment_url"].endswith(".pdf"))
        self.assertIsNone(body["image_url"])

    def test_notice_create_supports_multiple_locations(self):
        created = self.client.post(
            "/api/notices",
            data={
                "category": "notice",
                "title": "복수 위치 게시물",
                "location": "101동",
                "line": "1라인",
                "floor": "1층",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
                "location_targets_json": '[{"location":"101동","line":"1라인","floor":"1층"},{"location":"102동","line":"2라인","floor":"3층"}]',
            },
            files={"attachment": ("notice.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["created_count"], 2)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["attachment_filename"], "notice.pdf")
        self.assertEqual(body["items"][1]["location"], "102동")

        listing = self.client.get("/api/notices", params={"q": "복수 위치 게시물"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 2)

    def test_location_generator_supports_preview_and_insert(self):
        preview = self.client.post(
            "/api/notices/locations/generate",
            json={
                "buildings": "101-102",
                "lines": "1-2, 3-4라인",
                "floors": "B1, 1-3",
                "excluded_floors": "2층",
                "sort_order_start": 10,
                "dry_run": True,
            },
        )
        self.assertEqual(preview.status_code, 200)
        preview_body = preview.json()
        self.assertEqual(preview_body["preview_count"], 12)
        self.assertEqual(preview_body["items"][0]["building"], "101동")
        self.assertEqual(preview_body["items"][0]["line"], "1-2라인")
        self.assertEqual(preview_body["items"][0]["floor"], "B1")

        created = self.client.post(
            "/api/notices/locations/generate",
            json={
                "buildings": "101-102",
                "lines": "1-2, 3-4라인",
                "floors": "B1, 1-3",
                "excluded_floors": "2층",
                "sort_order_start": 10,
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["inserted"], 12)
        self.assertEqual(created.json()["skipped"], 0)

        locations = self.client.get("/api/notices/locations")
        self.assertEqual(locations.status_code, 200)
        tree = locations.json()["tree"]
        self.assertEqual(tree["101동"]["1-2라인"], ["B1", "1층", "3층"])

    def test_location_delete_by_building(self):
        created = self.client.post(
            "/api/notices/locations/generate",
            json={
                "buildings": "101-102",
                "lines": "1라인",
                "floors": "1-2",
            },
        )
        self.assertEqual(created.status_code, 200)

        deleted = self.client.delete("/api/notices/locations/building/101동")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["building"], "101동")

        locations = self.client.get("/api/notices/locations")
        tree = locations.json()["tree"]
        self.assertNotIn("101동", tree)
        self.assertIn("102동", tree)

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
