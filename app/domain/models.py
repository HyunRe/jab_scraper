from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Job:
    id: str
    platform: str
    title: str
    company: str
    url: str
    location: Optional[str] = "정보 없음"         # 근무 위치
    required_experience: Optional[str] = "무관"  # 요구 경력
    deadline: Optional[str] = "상시 채용"
    detail_text: Optional[str] = ""

@dataclass
class JobEvaluation:
    job: Job
    score: str                                  # '상', '중', '하'
    match_or_lack_reason: str                   # 적합성 또는 부족한 점
    matching_tech_stacks: List[str]             # 일치하는 주요 기술 스택
    customized_resume_summary_html: str         # JD에 맞게 재구성된 이력서 핵심 기술 요약 및 성과 (HTML)
    customized_cover_letter_html: str           # 전면 각색된 자소서 전체 (HTML, blue/red 마킹)
    matched_domain: str = ""                    # 매핑된 도메인 정보