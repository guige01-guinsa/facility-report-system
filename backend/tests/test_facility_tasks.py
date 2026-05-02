import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import facility_tasks
from app.main import app


class FacilityTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = facility_tasks.DB_PATH
        self.original_upload_dir = facility_tasks.UPLOAD_DIR
        facility_tasks.DB_PATH = Path(self.temp_dir.name) / "facility-tasks.db"
        facility_tasks.UPLOAD_DIR = Path(self.temp_dir.name) / "uploads"
        facility_tasks.init_facility_task_db()
        self.client = TestClient(app)

    def tearDown(self):
        facility_tasks.DB_PATH = self.original_db_path
        facility_tasks.UPLOAD_DIR = self.original_upload_dir
        self.temp_dir.cleanup()

    def test_create_list_and_summary(self):
        created = self.client.post(
            "/api/facility-tasks",
            json={
                "title": "소방 종합정밀점검",
                "category": "fire",
                "priority": "statutory",
                "assignee": "시설과장",
                "due_date": "2026-05-03",
                "recurrence_type": "yearly",
                "reminder_days": [30, 7, 1, 0],
                "evidence_required": True,
            },
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["category_label"], "소방점검")
        self.assertTrue(body["evidence_required"])

        listing = self.client.get("/api/facility-tasks", params={"scope": "all"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)

        summary = self.client.get("/api/facility-tasks/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["statutory"], 1)
        self.assertEqual(summary.json()["evidence_required"], 1)

    def test_complete_monthly_task_advances_next_due_date(self):
        created = self.client.post(
            "/api/facility-tasks",
            json={
                "title": "펌프실 정기점검",
                "category": "regular",
                "due_date": "2026-05-03",
                "recurrence_type": "monthly",
            },
        )
        self.assertEqual(created.status_code, 200)
        task_id = created.json()["id"]

        completed = self.client.post(f"/api/facility-tasks/{task_id}/complete", data={"note": "완료"})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["next_task"]["due_date"], "2026-06-03")
        self.assertEqual(completed.json()["next_task"]["completion_count"], 1)

        history = self.client.get(f"/api/facility-tasks/{task_id}/completions")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["note"], "완료")

    def test_one_time_task_becomes_inactive_after_completion(self):
        created = self.client.post(
            "/api/facility-tasks",
            json={
                "title": "긴급 보수 확인",
                "category": "other",
                "due_date": "2026-05-03",
                "recurrence_type": "none",
            },
        )
        self.assertEqual(created.status_code, 200)
        task_id = created.json()["id"]

        completed = self.client.post(f"/api/facility-tasks/{task_id}/complete", data={"note": "처리"})
        self.assertEqual(completed.status_code, 200)
        self.assertFalse(completed.json()["next_task"]["active"])

    def test_evidence_required_rejects_completion_without_file(self):
        created = self.client.post(
            "/api/facility-tasks",
            json={
                "title": "법정 서류 제출",
                "category": "statutory",
                "priority": "statutory",
                "due_date": "2026-05-03",
                "recurrence_type": "yearly",
                "evidence_required": True,
            },
        )
        self.assertEqual(created.status_code, 200)
        task_id = created.json()["id"]

        completed = self.client.post(f"/api/facility-tasks/{task_id}/complete", data={"note": "완료"})
        self.assertEqual(completed.status_code, 400)

        completed_with_file = self.client.post(
            f"/api/facility-tasks/{task_id}/complete",
            data={"note": "완료"},
            files={"evidence": ("report.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
        self.assertEqual(completed_with_file.status_code, 200)


if __name__ == "__main__":
    unittest.main()

