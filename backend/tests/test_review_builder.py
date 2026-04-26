import unittest

from app.config import resolve_openai_model
from app.kakao_parser import parse_diagnostics, parse_kakao_chat
from app.review_builder import build_review_session, decode_uploaded_text


class ReviewBuilderTests(unittest.TestCase):
    def test_classifies_noise_and_matches_kakao_image_filename(self):
        text = "\n".join(
            [
                "2026. 4. 25. 오후 2:22, 김관리 : 확인했습니다",
                "2026. 4. 25. 오후 2:28, 이기사 : 101동 주차장 차단기 점검 완료했습니다",
                "2026. 4. 25. 오후 2:34, 김관리 : 감사합니다",
            ]
        )
        messages = parse_kakao_chat(text)
        review = build_review_session(
            messages,
            [{"filename": "KakaoTalk_20260425_143200123.jpg", "content_type": "image/jpeg", "size": 2048}],
            use_ai=False,
        )

        statuses = {message["message"]: message["status"] for message in review["messages"]}
        self.assertEqual(statuses["확인했습니다"], "excluded")
        self.assertEqual(statuses["감사합니다"], "excluded")

        work_message = next(message for message in review["messages"] if message["status"] == "work")
        self.assertIn("차단기", work_message["message"])
        self.assertEqual(review["matches"][0]["message_id"], work_message["id"])
        self.assertIn(review["matches"][0]["status"], {"confirmed", "needs_review"})

    def test_keeps_image_unmatched_without_time_signal(self):
        text = "2026. 4. 25. 오후 2:28, 이기사 : 101동 주차장 차단기 점검 완료했습니다"
        messages = parse_kakao_chat(text)
        review = build_review_session(
            messages,
            [{"filename": "site-photo.jpg", "content_type": "image/jpeg", "size": 2048}],
            use_ai=False,
        )

        self.assertIsNone(review["matches"][0]["message_id"])
        self.assertEqual(review["matches"][0]["status"], "unmatched")

    def test_decodes_korean_windows_export(self):
        raw = "2026. 4. 25. 오후 2:28, 이기사 : 점검 완료".encode("cp949")
        decoded = decode_uploaded_text(raw)
        self.assertIn("점검 완료", decoded)

    def test_openai_model_selection_is_limited_to_known_options(self):
        self.assertEqual(resolve_openai_model("gpt-5-mini"), "gpt-5-mini")
        self.assertEqual(resolve_openai_model("unknown-model"), "gpt-5-nano")

    def test_parses_additional_kakao_export_date_formats(self):
        korean_date = "2026년 4월 25일 오후 2:28, 이기사 : 차단기 점검 완료"
        bracket_date = "[이기사] [2026. 4. 25. 오후 2:29] 차단기 사진 확인"

        first = parse_kakao_chat(korean_date)
        second = parse_kakao_chat(bracket_date)

        self.assertEqual(first[0]["datetime"], "2026-04-25T14:28")
        self.assertEqual(first[0]["message"], "차단기 점검 완료")
        self.assertEqual(second[0]["datetime"], "2026-04-25T14:29")
        self.assertEqual(second[0]["user"], "이기사")

    def test_parses_plain_date_header_with_time_rows(self):
        text = "\n".join(
            [
                "2026년 4월 25일 토요일",
                "오후 2:28, 이기사 : 차단기 점검 완료",
                "[오후 2:29] 김관리 : 사진 확인했습니다",
            ]
        )

        messages = parse_kakao_chat(text)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["datetime"], "2026-04-25T14:28")
        self.assertEqual(messages[1]["user"], "김관리")

    def test_parse_diagnostics_masks_preview(self):
        diagnostics = parse_diagnostics("010-1234-5678\n12가3456")

        self.assertIn("***-****-****", diagnostics["preview_lines"][0])
        self.assertIn("***차****", diagnostics["preview_lines"][1])


if __name__ == "__main__":
    unittest.main()
