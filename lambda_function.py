import os
import re
from dataclasses import asdict
from typing import Any, List, Dict, Optional, cast

from app.infrastructure.collectors.wanted_collector import WantedCollector
from app.infrastructure.collectors.saramin_collector import SaraminCollector
from app.infrastructure.collectors.jumpit_collector import JumpitCollector
from app.infrastructure.collectors.jobkorea_collector import JobKoreaCollector
from app.infrastructure.collectors.rallit_collector import RallitCollector
from app.infrastructure.collectors.jasoseol_collector import JasoseolCollector
from app.infrastructure.composite_collector import CompositeJobCollector
from app.infrastructure.file_repository import LocalFileRepository
from app.infrastructure.deduplicator import JobDeduplicator

from app.presentation.notion_scripter_notifier import NotionScripterNotifier
from app.presentation.email_notifier import EmailNotifier
from app.domain.models import Job


def is_target_job(item: Dict[str, Any] | Job, deduplicator: Optional[JobDeduplicator] = None) -> bool:
    """1차 파이썬 필터링: 수도권 지역, 3년 이하/신입 타겟 및 마감일 미경과 공고 필터링"""
    loc = item.get("location", "") if isinstance(item, dict) else getattr(item, "location", "")
    exp = item.get("required_experience", "") if isinstance(item, dict) else getattr(item, "required_experience", "")
    title = item.get("title", "") if isinstance(item, dict) else getattr(item, "title", "")
    deadline = item.get("deadline", "") if isinstance(item, dict) else getattr(item, "deadline", "")

    # 1. 마감일 검증 (deduplicator 파서 활용)
    if deduplicator and deduplicator.is_expired_deadline(deadline):
        return False

    # 2. 지역 조건 (수도권 주요 시/도 및 거점 IT 단지/구 단위 포함)
    allowed_regions = [
        "서울", "경기", "인천", "수도권",
        "강남", "구로", "가산", "판교", "분당", "마포",
        "상세 참조", "지역 정보 없음", "전체", "대한민국", ""
    ]
    if not any(r in loc for r in allowed_regions):
        return False

    # 3. 경력 조건 (신입 및 3년 이하, 1년 이하 타겟)
    exp_text = f"{exp} {title}".lower()

    # 허용 패턴 (신입, 주니어, 1년 이하, 1~3년 등)
    allow_patterns = [
        r"신입", r"주니어", r"junior",
        r"1\s*년\s*이하", r"1\s*년", r"2\s*년", r"3\s*년",
        r"인턴", r"경력\s*무관", r"무관"
    ]
    is_allowed = any(re.search(pat, exp_text) for pat in allow_patterns)

    # 거부 패턴 (4년 이상, 시니어, 팀장급 등)
    reject_patterns = [
        r"[4-9]\s*년",
        r"\d{2}\s*년",
        r"시니어", r"senior",
        r"lead", r"리드",
        r"팀장", r"차장", r"부장"
    ]

    for pattern in reject_patterns:
        if re.search(pattern, exp_text):
            # 신입/주니어/1년 이하 키워드가 포함되어 있다면 거부 패턴을 무시하고 통과
            if is_allowed:
                continue
            return False

    return True


def lambda_handler(event, context):
    print("[Lambda] 핸들러 실행 시작 (공고 수집 전용)")

    # 환경 변수 로드
    GMAIL_USER = os.environ.get("GMAIL_USER")
    GMAIL_PASS = os.environ.get("GMAIL_PASS")
    TO_EMAIL = os.environ.get("TO_EMAIL")
    NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
    NOTION_JOB_SCRIPTER_DB_ID = os.environ.get("NOTION_JOB_SCRIPTER_DB_ID") or os.environ.get("NOTION_DATABASE_ID")

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

    # 인프라 객체 생성
    file_repo = LocalFileRepository(asset_dir="assets")
    email_notifier = EmailNotifier(gmail_user=GMAIL_USER, gmail_pass=GMAIL_PASS, to_email=TO_EMAIL)
    deduplicator = JobDeduplicator(repo_slug=GITHUB_REPOSITORY, github_token=GITHUB_TOKEN)
    scripter_notifier = NotionScripterNotifier(NOTION_TOKEN, NOTION_JOB_SCRIPTER_DB_ID) if NOTION_TOKEN and NOTION_JOB_SCRIPTER_DB_ID else None

    # 신규 공고 수집, 1차 필터링, 노션 DB 1 저장 & 이메일 발송
    try:
        print("[Lambda] 전체 플랫폼 공고 수집 시작...")
        collectors = [
            WantedCollector(),
            SaraminCollector(),
            JumpitCollector(),
            JobKoreaCollector(),
            RallitCollector(),
            JasoseolCollector()
        ]
        job_collector = CompositeJobCollector(collectors)
        collected_jobs = job_collector.collect()

        # dict 형태만 가지는 리스트 생성
        def to_dict(job: Job | Dict[str, Any]) -> Dict[str, Any]:
            if isinstance(job, Job):
                return asdict(job)
            return job

        collected_dicts: List[Dict[str, Any]] = [
            to_dict(job)
            for job in collected_jobs
            if isinstance(job, (Job, dict))
        ]

        # GitHub JSON 기록 기반 1차 중복 및 마감일 필터링
        new_jobs = deduplicator.filter_new_jobs(collected_dicts)

        # 1차 조건 필터링 (지역/경력/마감일)
        filtered_jobs = [job for job in new_jobs if is_target_job(job, deduplicator=deduplicator)]
        print(f"[Lambda] 신규 수집 {len(new_jobs)}건 중 1차 조건 필터 통과: {len(filtered_jobs)}건")

        if filtered_jobs:
            job_objects: List[Job] = [
                Job(**item) if isinstance(item, dict) else cast(Job, cast(object, item))
                for item in filtered_jobs
            ]

            if job_objects:
                saved_jobs: List[Job] = job_objects
                # 1. 노션 DB 1(공고 스크립트)에 수집 공고 저장 (노션 공고명 중복 검사 2차 수행)
                if scripter_notifier:
                    res_saved = scripter_notifier.save_raw_jobs(jobs=job_objects, deduplicator=deduplicator)
                    saved_jobs = [
                        j if isinstance(j, Job) else Job(**j)
                        for j in res_saved
                    ]
                    print(f"[Notion DB 1] 최종 {len(saved_jobs)}건 공고 스크립트 DB 저장 완료")

                # 2. Daily 이메일 리포트 발송
                if GMAIL_USER and GMAIL_PASS and TO_EMAIL and saved_jobs:
                    email_notifier.send_daily_raw_report(saved_jobs)
                    print(f"[Email] {len(saved_jobs)}건 일일 공고 수집 리포트 발송 완료")

        return {
            "statusCode": 200,
            "body": "Successfully executed job collection and email notification."
        }

    except Exception as e:
        print(f"[Lambda 실행 중 예외 발생]: {e}")
        raise e