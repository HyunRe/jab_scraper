import pytest
from unittest.mock import MagicMock
from app.domain.models import Job
from app.infrastructure.llm_evaluator import GeminiLLMEvaluator


def test_gemini_json_parsing_with_malformed_string():
    print("\n[TEST START] Gemini JSON 파싱 예외 처리 테스트 시작")
    try:
        evaluator = GeminiLLMEvaluator.__new__(GeminiLLMEvaluator)

        bad_gemini_response = """
        ```json
        {
          "score": "상",
          "match_or_lack_reason": "백엔드 "성능 개선" 경험 우수",
          "matching_tech_stacks": ["Java", "Spring Boot", "Redis"],
          "customized_resume_summary_html": "**주요 기술 성과:** 응답 속도 개선",
          "customized_cover_letter_html": "**Spring Boot** 기반 확장성 설계"
        }
        ```
        """

        cleaned = evaluator._clean_json_text(bad_gemini_response)
        assert cleaned.startswith("{"), "클리닝 후 JSON 시작 위치 불일치"
        assert cleaned.endswith("}"), "클리닝 후 JSON 종료 위치 불일치"

        data = evaluator._safe_parse_json(cleaned)
        assert data["score"] == "상", f"점수 파싱 실패: {data.get('score')}"
        assert "Spring Boot" in data["customized_cover_letter_html"], "파싱 내용 누락"

        print("  └ [OK] 백틱 제거 및 JSON 큰따옴표 이스케이프 파싱 검증 완료")
        print("✅ [TEST SUCCESS] Gemini JSON 파싱 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] JSON 파싱 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e