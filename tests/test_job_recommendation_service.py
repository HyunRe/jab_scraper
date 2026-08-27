import unittest
from unittest.mock import MagicMock
from app.domain.models import Job, JobEvaluation
from app.application.job_recommendation_service import JobRecommendationService


class TestJobRecommendationService(unittest.TestCase):
    def setUp(self):
        self.mock_collector = MagicMock()
        self.mock_file_repo = MagicMock()
        self.mock_evaluator = MagicMock()
        self.mock_scripter_notifier = MagicMock()
        self.mock_analysis_notifier = MagicMock()

        self.service = JobRecommendationService(
            job_collector=self.mock_collector,
            file_repo=self.mock_file_repo,
            llm_evaluator=self.mock_evaluator,
            scripter_notifier=self.mock_scripter_notifier,
            analysis_notifier=self.mock_analysis_notifier
        )

    def test_evaluate_jobs_two_step_pipeline(self):
        print("\n================ [테스트 시작] 2단계 파이프라인 검증 ================")

        job1 = Job(id="1", platform="사람인", title="백엔드 1", company="A사", url="http://test.com/1", location="서울",
                   required_experience="경력", deadline="상시")
        job2 = Job(id="2", platform="원티드", title="백엔드 2", company="B사", url="http://test.com/2", location="서울",
                   required_experience="경력", deadline="상시")
        job3 = Job(id="3", platform="잡코리아", title="백엔드 3", company="C사", url="http://test.com/3", location="서울",
                   required_experience="경력", deadline="상시")

        jobs = [job1, job2, job3]

        self.mock_evaluator.evaluate_basic.side_effect = ['상', '하', '중']
        self.mock_evaluator.select_domain_and_version.return_value = ('backend', 'v1')
        self.mock_file_repo.read_asset.return_value = "mock template"

        eval1 = JobEvaluation(
            job=job1,
            score="상",
            matched_domain="사람인 / BACKEND (V1)",
            match_or_lack_reason="적합",
            matching_tech_stacks=["Java"],
            customized_resume_summary_html="<div>요약</div>",
            customized_cover_letter_html="<div>자소서</div>"
        )
        eval3 = JobEvaluation(
            job=job3,
            score="중",
            matched_domain="잡코리아 / BACKEND (V1)",
            match_or_lack_reason="보통",
            matching_tech_stacks=["Spring"],
            customized_resume_summary_html="<div>요약</div>",
            customized_cover_letter_html="<div>자소서</div>"
        )
        self.mock_evaluator.evaluate_and_customize.side_effect = [eval1, eval3]

        try:
            results = self.service.evaluate_jobs(jobs)

            self.assertEqual(self.mock_evaluator.evaluate_basic.call_count, 3)
            print("  ✔️ [통과] 1차 평가(evaluate_basic)가 모든 공고(3건)에 대해 정상 수행되었습니다.")

            self.assertEqual(self.mock_collector.fetch_job_detail.call_count, 2)
            print("  ✔️ [통과] 2단계 상세 수집 및 각색이 '상', '중' 등급 공고(2건)에 대해서만 수행되었습니다.")

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].job.company, "A사")
            self.assertEqual(results[1].job.company, "C사")
            print(f"  ✔️ [통과] 최종 결과 개수 일치 (총 {len(results)}건)")
            print("================ [테스트 성공] 모든 검증 항목을 통과했습니다. ================")

        except AssertionError as e:
            print(f"  ❌ [실패] 어설션 오류 발생: {e}")
            print("================ [테스트 실패] ================")
            raise e
        except Exception as e:
            print(f"  ❌ [오류] 예기치 않은 에러 발생: {e}")
            print("================ [테스트 오류] ================")
            raise e

    def test_process_analysis_for_job_page_duplicate_skip(self):
        print("\n================ [테스트 시작] DB2 중복 분석 건너뛰기 테스트 ================")
        page_id = "already_analyzed_page_id"

        self.mock_analysis_notifier.exists_by_original_page_id.return_value = True

        self.service.process_analysis_for_job_page(page_id)

        self.mock_analysis_notifier.exists_by_original_page_id.assert_called_once_with(page_id)
        self.mock_evaluator.evaluate_and_customize.assert_not_called()
        self.mock_analysis_notifier.save_evaluations.assert_not_called()

        # actual call 인자에 맞게 ("already_analyzed_page_id", "분석", "완료") 검증
        self.mock_scripter_notifier.update_status.assert_called_once_with(page_id, "분석", "완료")
        print("  ✔️ [통과] 이미 등록된 공고 스킵 및 DB1 상태 완료 업데이트 확인")

    def test_process_analysis_for_job_page_success(self):
        print("\n================ [테스트 시작] 신규 공고 분석 파이프라인 수행 테스트 ================")
        page_id = "new_job_page_id"

        # 0. 중복 체크 -> False (신규)
        self.mock_analysis_notifier.exists_by_original_page_id.return_value = False

        # 1. DB 1 조회 Mock 설정 (fetch_jobs_by_status)
        self.mock_scripter_notifier.fetch_jobs_by_status.return_value = [
            {
                "page_id": page_id,
                "company": "카카오",
                "title": "백엔드 개발자",
                "url": "http://test.com",
                "platform": "원티드",
                "location": "서울",
                "required_experience": "경력"
            }
        ]

        # 2. LLM 평가 관련 Mock 설정
        self.mock_evaluator.select_domain_and_version.return_value = ("backend", "v1")
        self.mock_file_repo.read_asset.return_value = "mock template"

        # id 키워드 인자로 전달 (page_id=page_id (X) -> id=page_id (O))
        job = Job(id=page_id, platform="원티드", title="백엔드 개발자", company="카카오", url="http://test.com")
        mock_eval = JobEvaluation(
            job=job, score="상", matched_domain="원티드 / BACKEND", match_or_lack_reason="적합",
            matching_tech_stacks=["Java"], customized_resume_summary_html="<b>요약</b>",
            customized_cover_letter_html="<b>자소서</b>"
        )
        self.mock_evaluator.evaluate_and_customize.return_value = mock_eval

        # 실행
        self.service.process_analysis_for_job_page(page_id)

        try:
            self.mock_analysis_notifier.exists_by_original_page_id.assert_called_once_with(page_id)
            self.mock_scripter_notifier.fetch_jobs_by_status.assert_called_once_with("분석", "요청")
            self.mock_evaluator.evaluate_and_customize.assert_called_once()
            self.mock_analysis_notifier.save_evaluations.assert_called_once_with([mock_eval], original_page_id=page_id)
            self.mock_scripter_notifier.update_status.assert_called_once_with(page_id, "분석", "완료")
            print("  ✔️ [통과] 신규 공고 분석 및 DB2 저장, 상태 업데이트 연동 성공")
        except AssertionError as e:
            print(f"  ❌ [실패 원인] {e}")
            raise e


if __name__ == "__main__":
    unittest.main()