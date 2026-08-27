from typing import List
from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository

class CompositeJobCollector(JobCollectorRepository):
    def __init__(self, collectors: List[JobCollectorRepository]):
        self.collectors = collectors

    def supports(self, platform: str) -> bool:
        return any(collector.supports(platform) for collector in self.collectors)

    def collect(self) -> List[Job]:
        return self.fetch_jobs()

    def fetch_jobs(self) -> List[Job]:
        all_jobs = []
        print("\n================ [채용 공고 수집 시작] ================")
        for collector in self.collectors:
            try:
                jobs = collector.fetch_jobs()
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"[{collector.__class__.__name__}] 수집 중 예외 발생: {e}")
        print(f"================ [총 수집 완료: {len(all_jobs)}건] ================\n")
        return all_jobs

    def fetch_job_detail(self, job: Job) -> str:
        for collector in self.collectors:
            if collector.supports(job.platform):
                return collector.fetch_job_detail(job)
        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 마감일: {job.deadline}"