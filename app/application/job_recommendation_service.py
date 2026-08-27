from typing import List, Optional, Any
from app.domain.models import Job, JobEvaluation
from app.domain.interfaces import JobCollectorRepository, FileRepository, LLMEvaluator


class JobRecommendationService:
    def __init__(
        self,
        job_collector: Optional[JobCollectorRepository] = None,
        file_repo: Optional[FileRepository] = None,
        llm_evaluator: Optional[LLMEvaluator] = None,
        email_notifier: Optional[Any] = None,
        analysis_notifier: Optional[Any] = None,
        deduplicator: Optional[Any] = None,
        scripter_notifier: Optional[Any] = None,
    ):
        self.job_collector = job_collector
        self.file_repo = file_repo
        self.llm_evaluator = llm_evaluator
        self.email_notifier = email_notifier
        self.analysis_notifier = analysis_notifier
        self.deduplicator = deduplicator
        self.scripter_notifier = scripter_notifier

    def _get_platform_resume(self, platform: str, domain: str) -> str:
        """도메인별 원본 이력서와 구직 사이트 규격 서식을 합성하여 반환"""
        if not self.file_repo:
            return ""

        # 1. 지원자 도메인별 원본 이력서 로드
        domain_resume = self.file_repo.read_asset(f"resume_{domain}.txt")

        # 2. 구직 사이트별 규격 양식 로드
        platform_format = ""
        if hasattr(self.file_repo, "get_resume_parser"):
            parser = self.file_repo.get_resume_parser()
            if parser:
                platform_format = parser.get_resume_for_platform(platform)

        # 3. 도메인 이력서 정보와 구직사이트 서식 정보를 함께 결합하여 LLM에 제공
        if domain_resume and platform_format:
            return (
                f"[지원자 원본 이력서 ({domain})]\n"
                f"{domain_resume}\n\n"
                f"[구직 사이트({platform}) 이력서 규격 양식]\n"
                f"{platform_format}"
            ).strip()

        return domain_resume or platform_format

    def _get_cover_letter_template(self, domain: str, version: str) -> str:
        """선택된 도메인/버전의 원본 자소서와 공통 작성 규칙(cover_letter_template.txt) 바인딩"""
        if not self.file_repo:
            return ""

        cover_text = self.file_repo.read_asset(f"cover_{domain}_{version}.txt")

        template_text = ""
        if hasattr(self.file_repo, "get_cover_letter_template"):
            template_text = self.file_repo.get_cover_letter_template()
        else:
            template_text = self.file_repo.read_asset("cover_letter_template.txt")

        if cover_text:
            return f"[공통 작성 규칙 및 4개 항목 규격]\n{template_text}\n\n[지원자 원본 자소서 내용]\n{cover_text}".strip()

        return template_text

    def process_analysis_for_job_page(self, page_id: str):
        """단일 DB 1 페이지 ID를 받아 중복 검사 -> 공고 분석 -> DB 2 저장 -> DB 1 상태 변경('완료') 진행"""
        if not self.scripter_notifier or not self.analysis_notifier or not self.llm_evaluator:
            print("[Service] 필수 컴포넌트(scripter_notifier, analysis_notifier, llm_evaluator)가 부족합니다.")
            return

        # 0. 중복 검사: DB 2에 이미 이 DB 1 페이지(page_id)에 대한 분석 결과가 존재하는지 확인
        if hasattr(self.analysis_notifier, "exists_by_original_page_id") and self.analysis_notifier.exists_by_original_page_id(page_id):
            print(f"[Service Skip] 이미 DB 2에 분석 데이터가 존재합니다 (page_id: {page_id}). DB 1 상태를 '완료'로 변경합니다.")
            if hasattr(self.scripter_notifier, "update_status"):
                self.scripter_notifier.update_status(page_id, "분석", "완료")
            return

        # 1. DB 1에서 해당 페이지 정보 조회
        jobs = self.scripter_notifier.fetch_jobs_by_status("분석", "요청")
        target_job = next((j for j in jobs if j.get("page_id") == page_id), None)

        if not target_job:
            print(f"[Service] DB 1에서 해당 page_id({page_id})의 공고를 찾을 수 없습니다.")
            return

        # 2. Job 객체 구성 (target_job의 platform 값을 정규화하여 설정)
        raw_platform = target_job.get("platform", "기타")
        platform_str = raw_platform.upper() if isinstance(raw_platform, str) else "기타"

        job_obj = Job(
            company=target_job.get("company", ""),
            title=target_job.get("title", ""),
            url=target_job.get("url", ""),
            id=page_id,
            platform=platform_str,
            location=target_job.get("location", ""),
            required_experience=target_job.get("required_experience", ""),
            detail_text=target_job.get("title", "")
        )

        try:
            # 3. 상세 본문 보완 (필요 시)
            if not job_obj.detail_text and self.job_collector:
                job_obj.detail_text = self.job_collector.fetch_job_detail(job_obj)

            # 4. 6개 도메인 x 2개 버전 최적 조합 선별
            domain, version = self.llm_evaluator.select_domain_and_version(job_obj)

            # 5. 플랫폼 이력서 & 자소서 템플릿 로드
            resume_text = self._get_platform_resume(job_obj.platform, domain)
            cover_text = self._get_cover_letter_template(domain, version)

            # 6. LLM 각색 및 평가
            evaluation = self.llm_evaluator.evaluate_and_customize(job_obj, resume_text, cover_text)
            evaluation.matched_domain = f"{job_obj.platform.upper()} / {domain.upper()} ({version.upper()})"

            # 7. DB 2에 저장
            self.analysis_notifier.save_evaluations([evaluation], original_page_id=page_id)
            print(f"[Service] 공고 분석 완료 및 DB 2 저장: {job_obj.company} - {job_obj.title}")

            # 8. 처리 완료 후 DB 1 상태를 '완료'로 업데이트
            if hasattr(self.scripter_notifier, "update_status"):
                self.scripter_notifier.update_status(page_id, "분석", "완료")

        except Exception as e:
            print(f"[Service Warning] 공고 단일 분석 실패 ({job_obj.company} - {job_obj.title}): {e}")

    def process_requested_analyses(self):
        """배치 동기화: DB 1에서 '분석' = '요청' 상태인 모든 공고를 일괄 분석"""
        if not self.scripter_notifier or not self.analysis_notifier:
            return

        requested_jobs = self.scripter_notifier.fetch_jobs_by_status("분석", "요청")
        if not requested_jobs:
            print("[Service] 현재 '분석' = '요청' 상태인 공고가 없습니다.")
            return

        print(f"[Service] 일괄 분석 요청 감지: 총 {len(requested_jobs)}건 처리 시작")
        for job_info in requested_jobs:
            page_id = job_info.get("page_id")
            if page_id:
                self.process_analysis_for_job_page(page_id)

    def evaluate_jobs(self, jobs: List[Job]) -> List[JobEvaluation]:
        """2단계 파이프라인: 1차 기본 정보 선별 -> 2차 통과 공고 대상 상세 수집 및 각색"""
        evaluations = []

        if not self.llm_evaluator:
            return evaluations

        # [1단계] 공고 기본 정보만으로 1차 선별 / 평가
        print(f"\n[1단계] 수집된 공고 {len(jobs)}건에 대한 기본 정보 1차 평가를 시작합니다.")
        passed_jobs = []

        for job in jobs:
            try:
                score = self.llm_evaluator.evaluate_basic(job) if hasattr(self.llm_evaluator, "evaluate_basic") else '상'
                if score in ['상', '중']:
                    passed_jobs.append(job)
                else:
                    print(f"[1단계 탈락] {job.company} - {job.title} (등급: {score})")
            except Exception as e:
                print(f"[Warning] 1단계 평가 실패 ({job.company} - {job.title}): {e}")
                continue

        print(f"[1단계 완료] 총 {len(jobs)}건 중 {len(passed_jobs)}건 통과 (2단계 진행)")

        # [2단계] 통과된 공고 대상 상세 본문 수집 및 자소서/이력서 각색
        for job in passed_jobs:
            try:
                if not job.detail_text and self.job_collector:
                    job.detail_text = self.job_collector.fetch_job_detail(job)

                if not job.detail_text:
                    print(f"[Skip] 2단계 본문 수집 실패: {job.company} - {job.title}")
                    continue

                domain, version = self.llm_evaluator.select_domain_and_version(job)
                resume_text = self._get_platform_resume(job.platform, domain)
                cover_text = self._get_cover_letter_template(domain, version)

                evaluation = self.llm_evaluator.evaluate_and_customize(job, resume_text, cover_text)
                evaluation.matched_domain = f"{job.platform.upper()} / {domain.upper()} ({version.upper()})"

                evaluations.append(evaluation)

            except Exception as e:
                print(f"[Warning] 2단계 각색 실패 ({job.company} - {job.title}): {e}")
                continue

        return evaluations

    def execute_recommendation_flow(self) -> List[JobEvaluation]:
        """공고 수집부터 평가까지 전체 파이프라인 실행"""
        if not self.job_collector:
            return []
        jobs = self.job_collector.fetch_jobs()
        return self.evaluate_jobs(jobs)