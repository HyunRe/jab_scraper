import unittest
from unittest.mock import MagicMock, patch
from app.domain.models import Job
from lambda_function import lambda_handler


class TestJobFilteringAndChunking:
    @patch("lambda_function.NotionScripterNotifier")
    @patch("lambda_function.JobDeduplicator")
    @patch("lambda_function.CompositeJobCollector")
    @patch("lambda_function.EmailNotifier")
    @patch("lambda_function.LocalFileRepository")
    def test_chunk_processing_with_60_jobs(
        self,
        mock_repo,
        mock_email_cls,
        mock_collector_cls,
        mock_dedup_cls,
        mock_scripter_cls,
    ):
        """총 60개의 필터 통과 공고가 들어왔을 때 수집, 중복제거, 노션 DB1 적재 및 이메일 발송 검증"""

        # 60개의 테스트용 주니어 공고 생성
        dummy_jobs = [
            Job(
                id=str(i),
                platform="원티드",
                title=f"주니어 백엔드 개발자 {i}",
                company=f"테스트기업 {i}",
                url=f"https://example.com/{i}",
                location="서울 강남구",
                required_experience="신입~2년",
                deadline="상시 채용"  # 마감일 필더 통과용 데이터 추가
            )
            for i in range(1, 61)
        ]

        # Mock 인프라 설정
        mock_collector = MagicMock()
        mock_collector.collect.return_value = dummy_jobs
        mock_collector_cls.return_value = mock_collector

        mock_dedup = MagicMock()
        mock_dedup.filter_new_jobs.side_effect = lambda jobs: jobs  # 중복 없음 처리
        mock_dedup.is_expired_deadline.return_value = False  # 마감일 미경과 처리
        mock_dedup_cls.return_value = mock_dedup

        # NotionScripterNotifier Mock 설정 (저장 성공 시 전달받은 jobs 반환)
        mock_scripter_instance = MagicMock()
        mock_scripter_instance.save_raw_jobs.side_effect = lambda jobs, **kwargs: jobs
        mock_scripter_cls.return_value = mock_scripter_instance

        # EmailNotifier Mock 설정
        mock_email_instance = MagicMock()
        mock_email_cls.return_value = mock_email_instance

        event, context = {}, {}

        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test_key",
                "GMAIL_USER": "test@gmail.com",
                "GMAIL_PASS": "test_pass",
                "TO_EMAIL": "target@gmail.com",
                "NOTION_TOKEN": "test_token",
                "NOTION_JOB_SCRIPTER_DB_ID": "mock_scripter_db_id",
                "NOTION_JOB_ANALYSIS_DB_ID": "mock_analysis_db_id",
                "NOTION_INTERVIEW_PREP_DB_ID": "mock_interview_prep_db_id",
            },
        ):
            response = lambda_handler(event, context)

        # 검증
        assert response["statusCode"] == 200
        assert mock_collector.collect.call_count == 1
        assert mock_scripter_instance.save_raw_jobs.call_count == 1
        assert mock_email_instance.send_daily_raw_report.call_count == 1