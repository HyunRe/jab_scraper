import os
from datetime import datetime, timedelta
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JobplanetCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.api_url = "https://www.jobplanet.co.kr/api/v3/job/postings"
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.jobplanet.co.kr/job",
            "jp-os-type": "web",
            "jp-ssr-auth": "jobplanet_desktop_ssr_1d6f8a5f219176accbb8fe051729fc6a"
        }

    def supports(self, platform: str) -> bool:
        return platform == "잡플래닛"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 형식으로 파싱 및 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        now = datetime.now()

        # 1. '오늘 마감', '내일 마감' 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        elif "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. 기타 상대 시간 표현(예: '3일 전', '2시간 전') 처리
        if any(
            keyword in cleaned
            for keyword in ["전", "일 전", "시간 전", "분 전"]
        ):
            return "상시 채용"

        if "상시" in cleaned or "채용시" in cleaned or "채용 시" in cleaned:
            return "상시 채용"

        # 3. 날짜 형식 파싱 시도 (예: '2026.04.15', '04/15', '4월 15일' 등)
        try:
            # 연도가 포함된 형식 (예: 2026.04.15 또는 2026-04-15)
            match_full = re.search(
                r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", cleaned
            )
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일만 있는 형식 (예: 04/15 또는 4월 15일)
            match_md = re.search(r"(\d{1,2})[./월]\s*(\d{1,2})일?", cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                dt = datetime(now.year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[잡플래닛] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="잡플래닛",
                    title="[CI Mock] 잡플래닛 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.jobplanet.co.kr/job/postings/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "occupation_level1": "",
                "occupation_level2": "11904",  # 백엔드/개발 세부 카테고리
                "years_of_experience": "",
                "review_score": "",
                "job_type": "",
                "city": "",
                "education_level_id": "",
                "order_by": "aggressive",
                "page": 1,
                "page_size": 30
            }

            res = requests.get(
                self.api_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                json_res = res.json() if isinstance(res.json(), dict) else {}
                recruits = json_res.get("data", {}).get("recruits", []) if isinstance(json_res.get("data"),
                                                                                      dict) else []

                for item in recruits:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("title") or "제목 없음").strip()

                    company_info = item.get("company", {}) or {}
                    company = str(company_info.get("name") or "기업명 미상").strip()

                    cities = item.get("cities") or []
                    location = ", ".join(cities) if isinstance(cities, list) and cities else "상세 참조"

                    career_text = item.get("career_text")
                    req_exp = str(career_text).strip() if career_text else "경력 무관"

                    # 마감일 포맷 통일 함수 적용
                    raw_deadline = item.get("deadline_message") or item.get("due_date") or ""
                    deadline = self._format_deadline(str(raw_deadline))

                    job_url = f"https://www.jobplanet.co.kr/job/postings/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="잡플래닛",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[잡플래닛] 수집 완료: {len(jobs)}건")
            else:
                print(f"[잡플래닛] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[잡플래닛] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """잡플래닛 공고 상세 정보 조회"""
        try:
            res = requests.get(
                job.url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = soup.select_one("div.recruitment_detail") or soup.select_one("section.job_description")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[잡플래닛] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"