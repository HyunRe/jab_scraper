from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any
from app.domain.models import Job, JobEvaluation

class JobCollectorRepository(ABC):
    @abstractmethod
    def fetch_jobs(self) -> List[Job]:
        pass

    @abstractmethod
    def fetch_job_detail(self, job: Job) -> str:
        pass

    @abstractmethod
    def supports(self, platform: str) -> bool:
        """해당 수집기가 특정 플랫폼(원티드, 점핏, 렐릿 등)을 처리할 수 있는지 여부"""
        pass

class FileRepository(ABC):
    @abstractmethod
    def read_asset(self, filename: str) -> str:
        pass

    @abstractmethod
    def get_resume_parser(self) -> Optional[Any]:
        pass

    @abstractmethod
    def get_cover_letter_template(self) -> str:
        pass

class LLMEvaluator(ABC):
    @abstractmethod
    def select_domain_and_version(self, job: Job) -> Tuple[str, str]:
        pass

    @abstractmethod
    def evaluate_and_customize(self, job: Job, resume_text: str, cover_text: str) -> JobEvaluation:
        pass