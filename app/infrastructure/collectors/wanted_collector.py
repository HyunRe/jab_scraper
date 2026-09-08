import os
from datetime import datetime, timedelta
import re
from typing import List
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class WantedCollector(JobCollectorRepository):
    def __init__(self):
        self.url = "https://www.wanted.co.kr/api/v4/jobs"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.wanted.co.kr/wdlist/518/872",
            "Origin": "https://www.wanted.co.kr",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def supports(self, platform: str) -> bool:
        return platform == "원티드"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
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

        # 3. 상대 시간 및 상시 채용 키워드 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 형식 파싱 시도
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
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[원티드] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="원티드",
                    title="[CI Mock] 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.wanted.co.kr/wd/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs = []
        try:
            params = {
                "country": "kr",
                "tag_type_ids": "872",
                "job_sort": "company.response_rate_order",
                "locations": "all",
                "limit": "30",
                "offset": "0",
            }

            print(f"\n================ [원티드 요청 디버그] ================")
            print(f"Request URL: {self.url}")
            print(f"Request Params: {params}")

            res = requests.get(
                self.url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10,
            )

            print(f"Response Status Code: {res.status_code}")
            print(f"Response Headers: {dict(res.headers)}")

            if res.status_code == 200:
                response_json = res.json() if isinstance(res.json(), dict) else {}
                data = response_json.get("data", []) if isinstance(response_json.get("data"), list) else []

                for item in data:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id", "") or "").strip()
                    if not job_id:
                        continue

                    # 방어적 기본값 파싱
                    title = str(item.get("position") or "제목 없음").strip()

                    company_info = item.get("company")
                    company_name = "기업명 미상"
                    if isinstance(company_info, dict):
                        company_name = str(company_info.get("name") or "기업명 미상").strip()

                    due_time = item.get("due_time")
                    raw_deadline = str(due_time).strip() if due_time else ""
                    deadline = self._format_deadline(raw_deadline)

                    address_info = item.get("address")
                    location = "상세 참조"
                    if isinstance(address_info, dict):
                        location = str(address_info.get("location") or "상세 참조").strip()

                    jobs.append(
                        Job(
                            id=job_id,
                            platform="원티드",
                            title=title,
                            company=company_name,
                            url=f"https://www.wanted.co.kr/wd/{job_id}",
                            location=location,
                            required_experience="경력 무관",
                            deadline=deadline,
                        )
                    )
                print(f"[원티드] 수집 완료: {len(jobs)}건")
            else:
                print(f"[원티드] API 응답 에러 (Status Code: {res.status_code})")
                with open("wanted_error_403.html", "w", encoding="utf-8") as f:
                    f.write(res.text)
                print("⚠️ [원티드] 403 응답 본문이 'wanted_error_403.html'에 저장되었습니다.")
        except Exception as e:
            print(f"[원티드] 수집 오류: {e}")
        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        return f"직무명: {job.title} / 회사명: {job.company}"