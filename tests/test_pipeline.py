import pytest
from unittest.mock import MagicMock
from app.domain.models import Job, JobEvaluation
from app.infrastructure.resume_parser import ResumePlatformParser
from app.application.job_recommendation_service import JobRecommendationService


@pytest.fixture
def sample_resume_platforms_txt():
    return """
[통합 관리 데이터베이스 / Master Data]
이름: 홍길동
기술 스택: Java, Spring Boot, MySQL, Redis

======================================================================
1. WANTED (원티드)
- 원티드 맞춤 서식 및 프로젝트 요약
======================================================================
2. JOBKOREA (잡코리아)
- 잡코리아 맞춤 서식
======================================================================
3. SARAMIN (사람인)
- 사람인 맞춤 서식
======================================================================
4. JUMPIT (점핏)
- 점핏 맞춤 서식
======================================================================
5. RALLIT (렐릿)
- 렐릿 맞춤 서식
"""


def test_resume_parser_platform_mapping(sample_resume_platforms_txt):
    print("\n[TEST START] ResumePlatformParser 플랫폼별 매핑 테스트 시작")
    try:
        parser = ResumePlatformParser(sample_resume_platforms_txt)

        wanted_res = parser.get_resume_for_platform("wanted")
        saramin_res = parser.get_resume_for_platform("saramin")
        assert "1. WANTED (원티드)" in wanted_res, f"원티드 섹션 추출 실패: {wanted_res}"
        assert "3. SARAMIN (사람인)" in saramin_res, f"사람인 섹션 추출 실패: {saramin_res}"
        print("  └ [OK] 일반 플랫폼(WANTED, SARAMIN) 전용 서식 파싱 성공")

        jasoseol_res = parser.get_resume_for_platform("jasoseol")
        assert "통합 관리 데이터베이스 / Master Data" in jasoseol_res, "Master Data가 누락되었습니다."
        assert "1. WANTED (원티드)" not in jasoseol_res, "자소설 항목에 타 플랫폼 섹션이 포함되었습니다."
        print("  └ [OK] 자소설닷컴(JASOSEOL) 노션 Master Data 전용 파싱 성공")

        print("✅ [TEST SUCCESS] ResumePlatformParser 매핑 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] ResumePlatformParser 매핑 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e


def test_job_recommendation_service_evaluate_jobs():
    print("\n[TEST START] JobRecommendationService 평가 파이프라인 검증 시작")
    try:
        mock_collector = MagicMock()
        mock_file_repo = MagicMock()
        mock_llm_evaluator = MagicMock()
        mock_scripter_notifier = MagicMock() # ⭕ 추가
        mock_analysis_notifier = MagicMock() # ⭕ 추가

        job = Job(
            id="wanted_123",
            platform="wanted",
            title="백엔드 개발자",
            company="테스트 컴퍼니",
            url="https://example.com",
            detail_text="Spring Boot, Redis 경험자 우대"
        )

        mock_llm_evaluator.evaluate_basic.return_value = "상"

        mock_llm_evaluator.select_domain_and_version.return_value = ("commerce", "verA")
        mock_llm_evaluator.evaluate_and_customize.return_value = JobEvaluation(
            job=job,
            score="상",
            match_or_lack_reason="Spring Boot 및 Redis 스택 일치",
            matching_tech_stacks=["Java", "Spring Boot", "Redis"],
            customized_resume_summary_html="<div>이력서 요약</div>",
            customized_cover_letter_html="<div>자소서 내용</div>"
        )

        mock_file_repo.read_asset.return_value = "샘플 자소서 원본"

        service = JobRecommendationService(
            job_collector=mock_collector,
            file_repo=mock_file_repo,
            llm_evaluator=mock_llm_evaluator,
            scripter_notifier=mock_scripter_notifier, # ⭕ 추가
            analysis_notifier=mock_analysis_notifier # ⭕ 추가
        )

        evaluations = service.evaluate_jobs([job])

        assert len(evaluations) == 1, f"평가 결과 개수 불일치: expected 1, got {len(evaluations)}"
        assert evaluations[0].score == "상", f"점수 불일치: {evaluations[0].score}"
        assert evaluations[0].matched_domain == "WANTED / COMMERCE (VERA)", f"도메인 매핑 오류: {evaluations[0].matched_domain}"
        assert mock_llm_evaluator.evaluate_and_customize.called, "LLM Evaluator가 호출되지 않았습니다."

        print("  └ [OK] 공고 평가, 도메인 매핑 및 LLM 호칭 결과 검증 완료")
        print("✅ [TEST SUCCESS] JobRecommendationService 파이프라인 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] 파이프라인 평가 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e