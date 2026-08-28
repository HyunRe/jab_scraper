import os
import runpy
from unittest.mock import patch, MagicMock


def test_main_execution_pipeline():
    print("\n[TEST START] main 스캔/동기화 파이프라인 통합 실행 테스트 시작")

    mock_env = {
        "GEMINI_API_KEY": "mock_gemini_key",
        "NOTION_TOKEN": "mock_notion_token",
        "NOTION_JOB_SCRIPTER_DB_ID": "mock_scripter_db_id",
        "NOTION_JOB_ANALYSIS_DB_ID": "mock_analysis_db_id",
        "NOTION_INTERVIEW_PREP_DB_ID": "mock_interview_db_id",
        "GMAIL_USER": "test@gmail.com",
        "GMAIL_PASS": "mock_pass",
        "TO_EMAIL": "test@gmail.com"
    }

    with patch.dict(os.environ, mock_env), \
         patch("app.infrastructure.llm_evaluator.GeminiLLMEvaluator"), \
         patch("app.infrastructure.interview_preparer.InterviewPreparer"), \
         patch("requests.post") as mock_requests_post, \
         patch("app.presentation.notion_scripter_notifier.NotionScripterNotifier"), \
         patch("app.presentation.notion_analysis_notifier.NotionAnalysisNotifier") as mock_analysis_cls, \
         patch("app.presentation.notion_interview_notifier.NotionInterviewNotifier"), \
         patch("app.application.job_recommendation_service.JobRecommendationService") as mock_service_cls:

        mock_service_instance = MagicMock()
        mock_service_cls.return_value = mock_service_instance

        mock_analysis_instance = MagicMock()
        mock_analysis_cls.return_value = mock_analysis_instance
        mock_analysis_instance.fetch_applied_jobs.return_value = []

        try:
            # main.py 실행 (__name__ == '__main__' 블록 트리거)
            runpy.run_path("main.py", run_name="__main__")

            # DB 1 -> DB 2 '요청' 건 스캔 수행 확인 (서비스 메서드 호출 검증)
            mock_service_instance.process_requested_analyses.assert_called_once()
            print("  └ [OK] DB 1 -> DB 2 '요청' 건 스캔(process_requested_analyses) 실행 성공")

            # DB 2 -> DB 3 '지원 완료' 건 스캔 수행 확인 (AnalysisNotifier 조회 검증)
            mock_analysis_instance.fetch_applied_jobs.assert_called_once()
            print("  └ [OK] DB 2 -> DB 3 '지원 완료' 건 스캔(fetch_applied_jobs) 실행 성공")

            print("✅ [TEST SUCCESS] main 통합 테스트 통과!\n")

        except Exception as e:
            print(f"❌ [TEST FAIL 원인]: {e}\n")
            raise e