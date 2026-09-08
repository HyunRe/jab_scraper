import pytest
from curl_cffi import requests
import re

# 기존 수집기
from app.infrastructure.collectors.wanted_collector import WantedCollector
from app.infrastructure.collectors.jasoseol_collector import JasoseolCollector
from app.infrastructure.collectors.jumpit_collector import JumpitCollector
from app.infrastructure.collectors.jobkorea_collector import JobKoreaCollector
from app.infrastructure.collectors.saramin_collector import SaraminCollector
from app.infrastructure.collectors.rallit_collector import RallitCollector
from app.infrastructure.collectors.catch_collector import CatchCollector
from app.infrastructure.collectors.incruit_collector import IncruitCollector

# 신규 추가 수집기
from app.infrastructure.collectors.jobplanet_collector import JobplanetCollector
from app.infrastructure.collectors.linkareer_collector import LinkareerCollector
from app.infrastructure.collectors.linkedin_collector import LinkedinCollector
from app.infrastructure.collectors.remember_collector import RememberCollector
from app.infrastructure.collectors.zighang_collector import ZighangCollector


def _verify_collector_result(collector_name: str, jobs: list):
    """수집 결과에 대한 로깅 및 유효성 검증"""
    try:
        assert isinstance(jobs, list), f"[{collector_name}] 반환값은 list 객체여야 합니다."

        if len(jobs) == 0:
            print(f"⚠️  [{collector_name}] 수집된 공고가 0건입니다. (IP 차단, 키 미설정 또는 검색 결과 없음)")
        else:
            print(f"✅ [{collector_name}] 수집 성공: {len(jobs)}건")
            first_job = jobs[0]
            # 마감일(deadline) 정보 확인을 위해 로그 출력 추가
            print(
                f"  └ 첫번째 공고: {first_job.company} - {first_job.title} | 마감일: '{first_job.deadline}' ({first_job.url})")

            assert first_job.company, f"[{collector_name}] 회사명이 비어있습니다."
            assert first_job.title, f"[{collector_name}] 공고 제목이 비어있습니다."
            assert first_job.url, f"[{collector_name}] 공고 URL이 비어있습니다."

            # 마감일 포맷 검증 (~M/D(요일) 패턴 또는 상시 채용/빈값)
            deadline_pattern = r'^(~\d{1,2}/\d{1,2}\([월화수목금토일]\)|상시 채용|)$'
            assert re.match(deadline_pattern, first_job.deadline), \
                f"[{collector_name}] 마감일 포맷 불일치: '{first_job.deadline}'"

    except AssertionError as e:
        print(f"❌ [{collector_name}] 검증 실패: {e}")
        raise e


def test_wanted_collector_real_fetch():
    print("\n[TEST START] 원티드 수집기 테스트 시작")
    collector = WantedCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("원티드", jobs)


def test_jasoseol_collector_real_fetch():
    print("\n[TEST START] 자소설닷컴 수집기 테스트 시작")
    collector = JasoseolCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("자소설닷컴", jobs)


def test_jumpit_collector_real_fetch():
    print("\n[TEST START] 점핏 수집기 테스트 시작")
    collector = JumpitCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("점핏", jobs)


def test_jobkorea_collector_real_fetch():
    print("\n[TEST START] 잡코리아 수집기 테스트 시작")
    collector = JobKoreaCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("잡코리아", jobs)


def test_saramin_collector_real_fetch():
    print("\n[TEST START] 사람인 수집기 테스트 시작")
    collector = SaraminCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("사람인", jobs)


def test_rallit_collector_real_fetch():
    print("\n[TEST START] 렐릿 수집기 테스트 시작")
    collector = RallitCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("렐릿", jobs)


def test_catch_collector_real_fetch():
    print("\n[TEST START] 캐치 수집기 테스트 시작")
    collector = CatchCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("캐치", jobs)

    # 올바른 상세페이지 경로 (/RecruitInfoDetails/) 검증
    if jobs:
        first_job = jobs[0]
        assert "/RecruitInfoDetails/" in first_job.url, \
            f"[캐치] URL 포맷 오류 (404 원인): '{first_job.url}' -> '/RecruitInfoDetails/' 형태여야 합니다."
        print(f"🔍 [디버그] 캐치 정상 URL 확인: {first_job.url}")


def test_incruit_collector_real_fetch():
    print("\n[TEST START] 인크루트 수집기 테스트 시작")
    collector = IncruitCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("인크루트", jobs)


import re
import pytest
from app.infrastructure.collectors.jobplanet_collector import JobplanetCollector


def test_jobplanet_collector_real_fetch():
    print("\n[TEST START] 잡플래닛 수집기 테스트 시작")
    collector = JobplanetCollector()
    jobs = collector.fetch_jobs()

    # 0. 최소 수집 건수 검증 (SKIPPED 방지 및 수집 성공 강제)
    assert len(jobs) > 0, "[잡플래닛] 잡코리아 제외 후 수집된 순수 공고가 0건입니다. (API 요청 파라미터 점검 필요)"

    # 1. URL 포맷 경로 (/job/search?posting_ids%5B%5D=) 검증
    first_job = jobs[0]
    assert "/job/search?posting_ids%5B%5D=" in first_job.url, \
        f"[잡플래닛] URL 포맷 오류: '{first_job.url}' -> '/job/search?posting_ids%5B%5D=' 형태여야 합니다."
    print(f"🔍 [디버그] 잡플래닛 정상 URL 확인: {first_job.url}")

    # 2. 마감일 D-day 파싱 결과 검증 (~M/D(요일) 패턴 또는 상시 채용)
    deadline_pattern = r'^(~\d{1,2}/\d{1,2}\([월화수목금토일]\)|상시 채용)$'
    for job in jobs:
        assert re.match(deadline_pattern, job.deadline), \
            f"[잡플래닛] 마감일 D-day 파싱 오류: '{job.deadline}'"
    print(f"🔍 [디버그] 수집된 공고 {len(jobs)}건의 마감일 포맷 파싱 정상 확인")

    # 3. 잡코리아 연동 공고 제외 검증
    for job in jobs:
        assert "jobkorea" not in job.url.lower(), \
            f"[잡플래닛] 잡코리아 외부 링크 포함 에러: {job.url}"
        assert "잡코리아" not in job.title, \
            f"[잡플래닛] 잡코리아 공고 미제외 에러: {job.title}"
    print(f"🔍 [디버그] 잡코리아 연동 공고 제외 상태 정상 확인")


def test_linkareer_collector_real_fetch():
    print("\n[TEST START] 링커리어 수집기 테스트 시작")

    debug_res = requests.post(
        "https://api.linkareer.com/graphql",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Device": "web",
            "Origin": "https://linkareer.com",
            "Referer": "https://linkareer.com/",
        },
        json={
            "operationName": "RecruitList",
            "variables": {
                "filterBy": {
                    "activityTypeID": 5,
                    "industryCategoryIDs": [5]
                }
            },
            "query": """
            query RecruitList($filterBy: ActivityFilter) {
              activities(filterBy: $filterBy) {
                nodes {
                  id
                  title
                  organizationName
                }
              }
            }
            """
        },
        impersonate="chrome120",
        timeout=10
    )
    print(f"🔍 [디버그] 링커리어 응답 코드: {debug_res.status_code}")

    debug_body = debug_res.json() if debug_res.status_code == 200 else {}
    if "errors" in debug_body:
        pytest.fail(f"[링커리어] GraphQL 스키마 에러: {debug_body['errors']}")

    raw_nodes = debug_body.get("data", {}).get("activities", {}).get("nodes", [])
    print(f"🔍 [디버그] 원시 수집 건수: {len(raw_nodes)}건")
    if raw_nodes:
        sample = raw_nodes[0]
        print(f"🔍 [디버그] 샘플 노드: id={sample.get('id')} | title={sample.get('title')}")

    collector = LinkareerCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("링커리어", jobs)


def test_linkedin_collector_real_fetch():
    print("\n[TEST START] 링크드인 수집기 테스트 시작")
    collector = LinkedinCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("링크드인", jobs)


def test_remember_collector_real_fetch():
    print("\n[TEST START] 리멤버 수집기 테스트 시작")
    collector = RememberCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("리멤버", jobs)


def test_zighang_collector_real_fetch():
    print("\n[TEST START] 직행 수집기 테스트 시작")
    collector = ZighangCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("직행", jobs)