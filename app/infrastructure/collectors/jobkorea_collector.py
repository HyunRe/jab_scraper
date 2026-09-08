from datetime import datetime, timedelta
import re
from typing import List
from bs4 import BeautifulSoup
import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JobKoreaCollector(JobCollectorRepository):
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.jobkorea.co.kr/Search/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.url = "https://www.jobkorea.co.kr/Recruit/Home/_GI_List/"

    def supports(self, platform: str) -> bool:
        return platform == "잡코리아"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        now = datetime.now()

        # 1. 오늘/내일 마감 키워드 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        if "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. D-day 패턴 처리 (예: D-day, D-1, D-14)
        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        # 3. 상대 시간 표현('3일 전' 등) 및 상시 채용 문구 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 포맷 파싱
        try:
            # ISO 포맷 또는 연도 포함 날짜 (예: 2026-04-15)
            match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일 형식 (예: 04.15, 4/15, 4월 15일)
            match_md = re.search(r'(\d{1,2})[./월-]\s*(\d{1,2})일?', cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                dt = datetime(now.year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

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
            "profile": "0",
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
                    location = (
                        etc_cells[2]
                        if len(etc_cells) > 2
                        else (etc_cells[1] if len(etc_cells) > 1 else "지역 정보 없음")
                    )

                    # 마감일 추출 및 포맷 통일 적용
                    deadline_elem = row.select_one("td.odd span.date")
                    raw_deadline = deadline_elem.text.strip() if deadline_elem else ""
                    deadline = self._format_deadline(raw_deadline)

                    jobs.append(
                        Job(
                            id=job_id,
                            platform="잡코리아",
                            title=title,
                            company=company,
                            url=job_url,
                            location=location,
                            required_experience=experience,
                            deadline=deadline,
                        )
                    )

                print(f"[잡코리아] 수집 완료: {len(jobs)}건")
            else:
                print(f"[잡코리아] API 응답 에러 (Status: {res.status_code})")

        except Exception as e:
            print(f"[잡코리아] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"