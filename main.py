import os
import requests
from dotenv import load_dotenv

from app.infrastructure.file_repository import LocalFileRepository
from app.infrastructure.llm_evaluator import GeminiLLMEvaluator
from app.infrastructure.deduplicator import JobDeduplicator
from app.infrastructure.composite_collector import CompositeJobCollector
from app.infrastructure.interview_preparer import InterviewPreparer

from app.presentation.email_notifier import EmailNotifier
from app.presentation.notion_scripter_notifier import NotionScripterNotifier
from app.presentation.notion_analysis_notifier import NotionAnalysisNotifier
from app.presentation.notion_interview_notifier import NotionInterviewNotifier

from app.application.job_recommendation_service import JobRecommendationService

load_dotenv()


def _sync_requested_analyses(
    recommendation_service: JobRecommendationService,
    notion_token: str,
    db_id: str
):
    """DB 1에서 '분석' = '요청' 인 항목 스캔 및 AI 분석 수행"""
    print("[Main] DB 1 -> DB 2 '요청' 건 스캔 시작...")

    # 노션 DB 1 데이터 상태 및 실제 컬럼 이름 출력 (디버깅)
    try:
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        res = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=headers,
            json={"page_size": 1}
        )
        raw_sample = res.json()

        print("\n--- [DEBUG] DB 1에 존재하는 실제 컬럼(속성) 목록 ---")
        if raw_sample.get("results"):
            props = raw_sample["results"][0].get("properties", {})
            for prop_name, prop_data in props.items():
                print(f"컬럼명: [{prop_name}] | 타입: [{prop_data.get('type')}]")
        print("---------------------------------------------------\n")
    except Exception as err:
        print(f"[DEBUG] DB 1 검사 중 예외 발생: {err}")

    # '요청' 건 처리 서비스 호출
    recommendation_service.process_requested_analyses()


def _sync_completed_interviews(
    analysis_notifier: NotionAnalysisNotifier,
    interview_notifier: NotionInterviewNotifier,
    file_repo: LocalFileRepository,
    api_key: str
):
    """DB 2에서 '지원' = '지원 완료' 인 항목 중 DB 3에 없는 항목 면접 준비 생성"""
    print("[Main] DB 2 -> DB 3 '지원 완료' 건 스캔 시작...")
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


if __name__ == "__main__":
    print("[Main] 노션 요청 건 수집 및 분석 처리 실행 시작")

    # 환경 변수 로드 (기본값 설정으로 None 반환 방지)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GMAIL_USER = os.environ.get("GMAIL_USER", "")
    GMAIL_PASS = os.environ.get("GMAIL_PASS", "")
    TO_EMAIL = os.environ.get("TO_EMAIL", "")
    NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

    NOTION_JOB_SCRIPTER_DB_ID = os.environ.get("NOTION_JOB_SCRIPTER_DB_ID") or os.environ.get("NOTION_DATABASE_ID", "")
    NOTION_JOB_ANALYSIS_DB_ID = os.environ.get("NOTION_JOB_ANALYSIS_DB_ID", "")
    NOTION_INTERVIEW_PREP_DB_ID = os.environ.get("NOTION_INTERVIEW_PREP_DB_ID") or os.environ.get("NOTION_INTERVIEW_DB_ID", "")

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")

    # 1. 필요 인프라 객체 생성 (수집기 제외)
    file_repo = LocalFileRepository(asset_dir="assets")
    llm_evaluator = GeminiLLMEvaluator(api_key=GEMINI_API_KEY)
    email_notifier = EmailNotifier(gmail_user=GMAIL_USER, gmail_pass=GMAIL_PASS, to_email=TO_EMAIL)
    deduplicator = JobDeduplicator(repo_slug=GITHUB_REPOSITORY, github_token=GITHUB_TOKEN)

    # 2. 역할별 노션 Notifier 인스턴스 생성
    scripter_notifier = NotionScripterNotifier(NOTION_TOKEN, NOTION_JOB_SCRIPTER_DB_ID) if NOTION_TOKEN and NOTION_JOB_SCRIPTER_DB_ID else None
    analysis_notifier = NotionAnalysisNotifier(NOTION_TOKEN, NOTION_JOB_ANALYSIS_DB_ID) if NOTION_TOKEN and NOTION_JOB_ANALYSIS_DB_ID else None
    interview_notifier = NotionInterviewNotifier(NOTION_TOKEN, NOTION_INTERVIEW_PREP_DB_ID) if NOTION_TOKEN and NOTION_INTERVIEW_PREP_DB_ID else None

    # 3. 서비스 레이어 객체 조립 (수집 작업 없이 노션 동기화 전용)
    recommendation_service = JobRecommendationService(
        job_collector=CompositeJobCollector([]), # 빈 수집기 전달
        file_repo=file_repo,
        llm_evaluator=llm_evaluator,
        email_notifier=email_notifier,
        analysis_notifier=analysis_notifier,
        deduplicator=deduplicator,
        scripter_notifier=scripter_notifier
    )

    # 4. DB 1 -> DB 2 ('분석' == '요청' 항목 스캔 및 AI 분석 수행)
    if scripter_notifier and analysis_notifier and NOTION_TOKEN and NOTION_JOB_SCRIPTER_DB_ID:
        _sync_requested_analyses(
            recommendation_service=recommendation_service,
            notion_token=NOTION_TOKEN,
            db_id=NOTION_JOB_SCRIPTER_DB_ID
        )

    # 5. DB 2 -> DB 3 ('지원' == '지원 완료' 항목 스캔 및 면접 대비 생성)
    if analysis_notifier and interview_notifier and GEMINI_API_KEY:
        _sync_completed_interviews(
            analysis_notifier=analysis_notifier,
            interview_notifier=interview_notifier,
            file_repo=file_repo,
            api_key=GEMINI_API_KEY
        )

    print("[Main] 모든 요청 처리 작업 완료.")