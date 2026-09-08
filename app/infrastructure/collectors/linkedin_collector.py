import os
from datetime import datetime, timedelta
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class LinkedinCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        # 링크드인 공개 채용 검색 API URL
        self.base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.linkedin.com/jobs/search",
        }

    def supports(self, platform: str) -> bool:
        return platform == "링크드인"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일/작성일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        now = datetime.now()

        # 1. '오늘', '내일' 마감 키워드 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        if "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. D-day 패턴 처리 (예: 'D-1', 'D-day', 'D-0')
        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        # 3. 상대 시간 표현(영문/한글) 처리
        if any(keyword in cleaned.lower() for keyword in ["전", "ago", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        # 4. 상시 채용 키워드 처리
        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 5. 날짜 형식 파싱 시도
        try:
            # 연도가 포함된 형식 (예: 2026-04-15 또는 2026.04.15)
            match_full = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일만 있는 형식 (예: 04.15, 4/15, 4월 15일)
            match_md = re.search(r"(\d{1,2})[./월-]\s*(\d{1,2})일?", cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                dt = datetime(now.year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리 (타 수집기들과 동일 패턴)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[링크드인] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="링크드인",
                    title="[CI Mock] 링크드인 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.linkedin.com/jobs/view/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "keywords": "Backend Developer",
                "location": "South Korea",
                "start": 0
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                job_cards = soup.select("li")

                for card in job_cards:
                    # 1. 제목 및 URL
                    title_anchor = card.select_one("h3.base-search-card__title, a.base-card__full-link")
                    if not title_anchor:
                        continue

                    title = title_anchor.get_text(strip=True) or "제목 없음"

                    link_elem = card.select_one("a.base-card__full-link")
                    job_url = str(link_elem.get("href") or "").split("?")[0].strip() if link_elem else ""
                    if not job_url:
                        continue

                    # job_id 추출
                    try:
                        job_id = job_url.rstrip("/").split("-")[-1]
                    except Exception:
                        job_id = "0"

                    # 2. 기업명
                    company_anchor = card.select_one("h4.base-search-card__subtitle a, a.hidden-nested-link")
                    company = company_anchor.get_text(strip=True) if company_anchor else "기업명 미상"

                    # 3. 근무 위치
                    location_elem = card.select_one("span.job-search-card__location")
                    location = location_elem.get_text(strip=True) if location_elem else "상세 참조"

                    # 4. 작성일/마감일 extraction & datetime 속성 대응
                    date_elem = card.select_one("time.job-search-card__listdate, time.job-search-card__listdate--new")
                    raw_date = ""
                    if date_elem:
                        raw_date = str(date_elem.get("datetime") or date_elem.get_text(strip=True) or "")

                    deadline = self._format_deadline(raw_date)

                    jobs.append(Job(
                        id=job_id,
                        platform="링크드인",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience="경력 무관",
                        deadline=deadline
                    ))

                print(f"[링크드인] 크롤링 수집 완료: {len(jobs)}건")
            else:
                print(f"[링크드인] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[링크드인] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """링크드인 공고 상세 본문 파싱"""
        try:
            detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job.id}"
            res = requests.get(
                detail_url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = soup.select_one("div.show-more-less-html__markup") or soup.select_one(
                    "section.description")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[링크드인] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 마감일: {job.deadline}"