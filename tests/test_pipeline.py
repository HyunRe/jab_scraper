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
======================================================================
6. INCRUIT (인크루트)
- 인크루트 맞춤 서식
======================================================================
7. LINKAREER (링커리어)
- 링커리어 맞춤 서식
"""


def test_resume_parser_platform_mapping(sample_resume_platforms_txt):
    print("\n[TEST START] ResumePlatformParser 플랫폼별 매핑 테스트 시작")
    try:
        parser = ResumePlatformParser(sample_resume_platforms_txt)

        wanted_res = parser.get_resume_for_platform("wanted")
        saramin_res = parser.get_resume_for_platform("saramin")
        incruit_res = parser.get_resume_for_platform("incruit")

        assert "1. WANTED (원티드)" in wanted_res, f"원티드 섹션 추출 실패: {wanted_res}"
        assert "3. SARAMIN (사람인)" in saramin_res, f"사람인 섹션 추출 실패: {saramin_res}"
        assert "6. INCRUIT (인크루트)" in incruit_res, f"인크루트 섹션 추출 실패: {incruit_res}"
        print("  └ [OK] 전용 서식이 있는 플랫폼(WANTED, SARAMIN, INCRUIT 등) 파싱 성공")

        # 전용 서식이 없는 사이트 (예: REMEMBER, JASOSEOL) 테스트
        remember_res = parser.get_resume_for_platform("remember")
        jasoseol_res = parser.get_resume_for_platform("jasoseol")

        assert "통합 관리 데이터베이스 / Master Data" in remember_res, "Master Data가 누락되었습니다."
        assert "1. WANTED (원티드)" not in remember_res, "타 플랫폼 섹션이 포함되었습니다."
        assert "통합 관리 데이터베이스 / Master Data" in jasoseol_res, "Master Data가 누락되었습니다."
        print("  └ [OK] 전용 서식 없는 플랫폼 Master Data 전용 파싱 성공")

        print("✅ [TEST SUCCESS] ResumePlatformParser 매핑 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] ResumePlatformParser 매핑 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e