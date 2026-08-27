import requests
from typing import List
from datetime import datetime, timedelta, timezone
from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository

class JasoseolCollector(JobCollectorRepository):
    def __init__(self):
        self.url = "https://jasoseol.com/employment/calendar_list.json"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": "https://jasoseol.com/"
        }

    def supports(self, platform: str) -> bool:
        return platform == "자소설닷컴"

    def fetch_jobs(self) -> List[Job]:
        jobs = []
        try:
            now = datetime.now(timezone.utc)
            start_time = (now - timedelta(days=15)).strftime("%Y-%m-%dT15:00:00.000Z")
            end_time = (now + timedelta(days=20)).strftime("%Y-%m-%dT15:00:00.000Z")

            res = requests.post(self.url, headers=self.headers, json={"start_time": start_time, "end_time": end_time}, timeout=10)

            if res.status_code == 200:
                data = res.json()
                employments = data.get("employment", []) if isinstance(data, dict) else []
                keywords = ["백엔드", "backend", "server", "java", "spring", "서버", "개발"]

                for item in employments:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id", "")).strip()
                    if not job_id:
                        continue

                    # [방어 로직] 안전한 기본값 설정
                    title = str(item.get("title") or "제목 없음").strip()
                    company_name = str(item.get("name") or "기업명 미상").strip()

                    if any(kw.lower() in (title + company_name).lower() for kw in keywords):
                        deadline_raw = str(item.get("end_time") or "")
                        deadline = deadline_raw.split(".")[0].replace("T", " ") if deadline_raw else "상시 채용"

                        jobs.append(Job(
                            id=job_id,
                            platform="자소설닷컴",
                            title=title,
                            company=company_name,
                            url=f"https://jasoseol.com/recruit/{job_id}",
                            location="상세 참조",
                            required_experience="신입/경력 공채",
                            deadline=deadline
                        ))

                print(f"[자소설닷컴] 수집 완료: {len(jobs)}건")
        except Exception as e:
            print(f"[자소설닷컴] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """공고 상세 내용을 조회합니다."""
        # 자소설닷컴 상세 본문 수집 혹은 기본 상세 내용 반환 처리
        return f"[{job.title}] 상세 내용 및 자소서 항목"