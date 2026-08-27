import os
import re
import json
from dataclasses import asdict
from typing import Any, List, Dict

from app.infrastructure.collectors.wanted_collector import WantedCollector
from app.infrastructure.collectors.saramin_collector import SaraminCollector
from app.infrastructure.collectors.jumpit_collector import JumpitCollector
from app.infrastructure.collectors.jobkorea_collector import JobKoreaCollector
from app.infrastructure.collectors.rallit_collector import RallitCollector
from app.infrastructure.collectors.jasoseol_collector import JasoseolCollector
from app.infrastructure.composite_collector import CompositeJobCollector
from app.infrastructure.file_repository import LocalFileRepository
from app.infrastructure.llm_evaluator import GeminiLLMEvaluator
from app.infrastructure.deduplicator import JobDeduplicator
from app.infrastructure.interview_preparer import InterviewPreparer

# 역할별로 분리된 노션 Notifier 모듈들
from app.presentation.notion_scripter_notifier import NotionScripterNotifier
from app.presentation.notion_analysis_notifier import NotionAnalysisNotifier
from app.presentation.notion_interview_notifier import NotionInterviewNotifier

from app.presentation.email_notifier import EmailNotifier
from app.application.job_recommendation_service import JobRecommendationService
from app.domain.models import Job


def is_target_job(item) -> bool:
    """1차 파이썬 필터링: 수도권 지역 및 3년 이하/신입 타겟 공고 필터링"""
    loc = item.get("location", "") if isinstance(item, dict) else getattr(item, "location", "")
    exp = item.get("required_experience", "") if isinstance(item, dict) else getattr(item, "required_experience", "")
    title = item.get("title", "") if isinstance(item, dict) else getattr(item, "title", "")

    # 1. 지역 조건 (수도권 주요 시/도 및 거점 IT 단지/구 단위 포함)
    allowed_regions = [
        "서울", "경기", "인천", "수도권",
        "강남", "구로", "가산", "판교", "분당", "마포",
        "상세 참조", "지역 정보 없음", "전체", "대한민국", ""
    ]
    if not any(r in loc for r in allowed_regions):
        return False

    # 2. 경력 조건 (신입 및 3년 이하, 1년 이하 타겟)
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
    print("[Lambda] 핸들러 실행 시작")

    # 환경 변수 로드
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GMAIL_USER = os.environ.get("GMAIL_USER")
    GMAIL_PASS = os.environ.get("GMAIL_PASS")
    TO_EMAIL = os.environ.get("TO_EMAIL")
    NOTION_TOKEN = os.environ.get("NOTION_TOKEN")

    NOTION_JOB_SCRIPTER_DB_ID = os.environ.get("NOTION_JOB_SCRIPTER_DB_ID") or os.environ.get("NOTION_DATABASE_ID")
    NOTION_JOB_ANALYSIS_DB_ID = os.environ.get("NOTION_JOB_ANALYSIS_DB_ID")
    NOTION_INTERVIEW_PREP_DB_ID = os.environ.get("NOTION_INTERVIEW_PREP_DB_ID") or os.environ.get(
        "NOTION_INTERVIEW_DB_ID")

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

    # 1. 인프라 객체 생성
    file_repo = LocalFileRepository(asset_dir="assets")
    llm_evaluator = GeminiLLMEvaluator(api_key=GEMINI_API_KEY)
    email_notifier = EmailNotifier(gmail_user=GMAIL_USER, gmail_pass=GMAIL_PASS, to_email=TO_EMAIL)
    deduplicator = JobDeduplicator(repo_slug=GITHUB_REPOSITORY, github_token=GITHUB_TOKEN)

    # 노션 Notifier 객체 개별 생성
    scripter_notifier = NotionScripterNotifier(NOTION_TOKEN,
                                               NOTION_JOB_SCRIPTER_DB_ID) if NOTION_TOKEN and NOTION_JOB_SCRIPTER_DB_ID else None
    analysis_notifier = NotionAnalysisNotifier(NOTION_TOKEN,
                                               NOTION_JOB_ANALYSIS_DB_ID) if NOTION_TOKEN and NOTION_JOB_ANALYSIS_DB_ID else None
    interview_notifier = NotionInterviewNotifier(NOTION_TOKEN,
                                                 NOTION_INTERVIEW_PREP_DB_ID) if NOTION_TOKEN and NOTION_INTERVIEW_PREP_DB_ID else None

    # --- [A] API Gateway / Notion Webhook 실시간 이벤트 처리 ---
    if isinstance(event, dict) and event.get("body"):
        try:
            body = json.loads(event.get("body", "{}"))
            page_id = body.get("entity_id")
            properties = body.get("data", {}).get("properties", {})

            # 1) DB 1에서 '분석' = '요청' 변경 시
            analysis_status = properties.get("분석", {}).get("select", {}).get("name")
            if analysis_status == "요청" and page_id and analysis_notifier:
                print(f"[Webhook] 공고 분석 요청 감지 (Page ID: {page_id})")
                service = JobRecommendationService(
                    job_collector=CompositeJobCollector([]),
                    file_repo=file_repo,
                    llm_evaluator=llm_evaluator,
                    email_notifier=email_notifier,
                    analysis_notifier=analysis_notifier,
                    deduplicator=deduplicator,
                    scripter_notifier=scripter_notifier
                )
                service.process_analysis_for_job_page(page_id)
                return {"statusCode": 200, "body": json.dumps({"message": "Job analysis created successfully"})}

            # 2) DB 2에서 '지원' = '지원 완료' 변경 시
            apply_status = properties.get("지원", {}).get("select", {}).get("name")
            if apply_status == "지원 완료" and page_id and interview_notifier:
                print(f"[Webhook] 지원 완료 감지 -> 면접/코테 데이터 생성 (Page ID: {page_id})")
                interview_preparer = InterviewPreparer(api_key=GEMINI_API_KEY)
                resume_text = file_repo.get_resume()

                company = properties.get("회사명", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                title_text = properties.get("분석명", {}).get("title", [{}])[0].get("text", {}).get("content", "")

                prep_data = interview_preparer.generate_interview_prep(
                    company=company,
                    job_title=title_text,
                    jd_text=title_text,
                    resume_text=resume_text
                )

                interview_notifier.save_interview_prep(
                    company=company,
                    job_title=title_text,
                    prep_data=prep_data,
                    original_page_id=page_id
                )
                return {"statusCode": 200, "body": json.dumps({"message": "Interview prep created successfully"})}

        except Exception as webhook_err:
            print(f"[Webhook Handling Error]: {webhook_err}")

    # --- [B] 매일 08:00 신규 공고 수집, 1차 필터링, 노션 DB 1 저장 & 이메일 발송 ---
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

        # 1. dict 형태만 가지는 리스트 생성 (타입 좁히기)
        def to_dict(job: Job | Dict[str, Any]) -> Dict[str, Any]:
            if isinstance(job, Job):
                return asdict(job)
            return job

        collected_dicts: List[Dict[str, Any]] = [
            to_dict(job)
            for job in collected_jobs
            if isinstance(job, (Job, dict))
        ]

        new_jobs = deduplicator.filter_new_jobs(collected_dicts)

        # 1차 조건 필터링 (지역/경력)
        filtered_jobs = [job for job in new_jobs if is_target_job(job)]
        print(f"[Lambda] 신규 수집 {len(new_jobs)}건 중 1차 조건 필터 통과: {len(filtered_jobs)}건")

        if filtered_jobs:
            # 2. Job 객체만으로 구성된 명확한 List[Job] 변환
            job_objects: List[Job] = []
            for item in filtered_jobs:
                if isinstance(item, dict):
                    job_objects.append(Job(**item))
                elif isinstance(item, Job):
                    job_objects.append(item)

            if job_objects:
                # 1. 노션 DB 1(공고 스크립트)에 수집 공고 저장
                if scripter_notifier:
                    scripter_notifier.save_raw_jobs(jobs=job_objects, deduplicator=deduplicator)
                    print(f"[Notion DB 1] {len(job_objects)}건 공고 스크립트 DB 저장 완료")

                # 2. Daily 이메일 리포트 발송 (List[Job] 타입 전송)
                if GMAIL_USER and GMAIL_PASS and TO_EMAIL:
                    email_notifier.send_daily_raw_report(job_objects)
                    print(f"[Email] {len(job_objects)}건 일일 공고 수집 리포트 발송 완료")

        # --- [C] 주기적 배치 스캔 ---
        if scripter_notifier and analysis_notifier:
            _sync_requested_analyses(scripter_notifier, analysis_notifier, file_repo, llm_evaluator, deduplicator,
                                     email_notifier)

        if analysis_notifier and interview_notifier:
            _sync_completed_interviews(analysis_notifier, interview_notifier, file_repo, GEMINI_API_KEY)

        return {
            "statusCode": 200,
            "body": "Successfully executed job collection, email notification, and DB sync."
        }

    except Exception as e:
        print(f"[Lambda 실행 중 예외 발생]: {e}")
        raise e


def _sync_requested_analyses(scripter_notifier, analysis_notifier, file_repo, llm_evaluator, deduplicator,
                             email_notifier):
    """DB 1에서 '분석' = '요청' 인 항목에 대해 서비스 레이어를 통해 분석 수행"""
    service = JobRecommendationService(
        job_collector=CompositeJobCollector([]),
        file_repo=file_repo,
        llm_evaluator=llm_evaluator,
        email_notifier=email_notifier,
        analysis_notifier=analysis_notifier,
        deduplicator=deduplicator,
        scripter_notifier=scripter_notifier
    )
    service.process_requested_analyses()


def _sync_completed_interviews(analysis_notifier, interview_notifier, file_repo, api_key):
    """DB 2에서 '지원' = '지원 완료' 인 항목 중 DB 3에 없는 항목 면접 준비 생성"""
    applied_jobs = analysis_notifier.fetch_applied_jobs()
    existing_linked_ids = interview_notifier.fetch_existing_interview_prep_page_ids()

    if not applied_jobs:
        return

    interview_preparer = InterviewPreparer(api_key=api_key)
    resume_text = file_repo.get_resume()

    for item in applied_jobs:
        page_id = item["page_id"]
        if page_id not in existing_linked_ids:
            print(f"[Batch Sync] 지원 완료 항목 발견: {item.get('title_text')}")
            prep_data = interview_preparer.generate_interview_prep(
                company=item.get("company", ""),
                job_title=item.get("title_text", ""),
                jd_text=item.get("title_text", ""),
                resume_text=resume_text
            )
            interview_notifier.save_interview_prep(
                company=item.get("company", ""),
                job_title=item.get("title_text", ""),
                prep_data=prep_data,
                original_page_id=page_id
            )