import requests
from typing import List
from bs4 import BeautifulSoup

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JobKoreaCollector(JobCollectorRepository):
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.jobkorea.co.kr/Search/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest"
        }
        self.url = "https://www.jobkorea.co.kr/Recruit/Home/_GI_List/"

    def supports(self, platform: str) -> bool:
        return platform == "잡코리아"

    def fetch_jobs(self) -> List[Job]:
        jobs = []
        payload = {
            "isDefault": "true",
            "condition[duty]": "1000229",
            "condition[menucode]": "",
            "page": "1",
            "direct": "0",
            "order": "20",
            "pagesize": "40",
            "tabindex": "0",
            "onePick": "0",
            "confirm": "0",
            "profile": "0"
        }

        try:
            res = requests.post(self.url, headers=self.headers, data=payload, timeout=10)

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                job_rows = soup.select("tr.devloopArea")

                for row in job_rows:
                    title_elem = row.select_one("td.tplTit strong a.link")
                    if not title_elem:
                        continue

                    title = title_elem.text.strip() or "제목 없음"
                    href = str(title_elem.get("href") or "")
                    if not href:
                        continue

                    job_url = f"https://www.jobkorea.co.kr{href}" if href.startswith("/") else href

                    try:
                        job_id = href.split("/")[-1].split("?")[0]
                    except Exception:
                        job_id = "0"

                    company_elem = row.select_one("td.tplCo a.link")
                    company = company_elem.text.strip() if company_elem else "기업명 미상"

                    etc_cells = [
                        span.text.strip()
                        for span in row.select("td.tplTit p.etc span.cell")
                        if span.text.strip()
                    ]

                    experience = etc_cells[0] if len(etc_cells) > 0 else "경력 정보 없음"
                    location = etc_cells[2] if len(etc_cells) > 2 else (
                        etc_cells[1] if len(etc_cells) > 1 else "지역 정보 없음")

                    deadline_elem = row.select_one("td.odd span.date")
                    deadline = deadline_elem.text.strip() if deadline_elem else "상시 채용"

                    jobs.append(Job(
                        id=job_id,
                        platform="잡코리아",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=experience,
                        deadline=deadline
                    ))

                print(f"[잡코리아] 수집 완료: {len(jobs)}건")
            else:
                print(f"[잡코리아] API 응답 에러 (Status: {res.status_code})")

        except Exception as e:
            print(f"[잡코리아] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"