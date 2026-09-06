import pytest

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
            print(f"  └ 첫번째 공고: {first_job.company} - {first_job.title} ({first_job.url})")

            assert first_job.company, f"[{collector_name}] 회사명이 비어있습니다."
            assert first_job.title, f"[{collector_name}] 공고 제목이 비어있습니다."
            assert first_job.url, f"[{collector_name}] 공고 URL이 비어있습니다."
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


def test_incruit_collector_real_fetch():
    print("\n[TEST START] 인크루트 수집기 테스트 시작")
    collector = IncruitCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("인크루트", jobs)


def test_jobplanet_collector_real_fetch():
    print("\n[TEST START] 잡플래닛 수집기 테스트 시작")
    collector = JobplanetCollector()
    jobs = collector.fetch_jobs()
    _verify_collector_result("잡플래닛", jobs)


def test_linkareer_collector_real_fetch():
    print("\n[TEST START] 링커리어 수집기 테스트 시작")
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