import os
import re
from datetime import datetime, timedelta
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JobplanetCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.api_url = "https://www.jobplanet.co.kr/api/v3/job/postings"
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.jobplanet.co.kr/job",
            "jp-os-type": "web",
            "jp-ssr-auth": "jobplanet_desktop_ssr_1d6f8a5f219176accbb8fe051729fc6a"
        }

    def supports(self, platform: str) -> bool:
        return platform == "잡플래닛"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        now = datetime.now()

        # 1. '오늘', '내일', '모레' 등 구체적인 날짜 표현 우선 처리
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

        # 3. 상대 시간 및 상시 채용 키워드 처리 ('9999' 포함)
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 형식 파싱 시도
        try:
            match_full = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            match_md = re.search(r"(\d{1,2})[./월-]\s*(\d{1,2})일?", cleaned)
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
                    url="https://www.jobplanet.co.kr/job/search?posting_ids%5B%5D=mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        max_pages = 3

        for page in range(1, max_pages + 1):
            try:
                params = {
                    "query": "백엔드",  # 검색어 추가로 자체 공고 노출 비율 증가
                    "occupation_level1": "",
                    "occupation_level2": "11904",  # 개발/백엔드
                    "years_of_experience": "",
                    "review_score": "",
                    "job_type": "",
                    "city": "",
                    "education_level_id": "",
                    "order_by": "recent",  # 최신순 정렬
                    "page": page,
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
                    recruits = json_res.get("data", {}).get("recruits", []) if isinstance(json_res.get("data"), dict) else []

                    if not recruits:
                        break

                    for item in recruits:
                        if not isinstance(item, dict):
                            continue

                        # ========================================================
                        # [핵심 필터링] 잡코리아 연동 및 외부 링크 공고 원천 차단
                        # ========================================================
                        apply_type = str(item.get("posting_apply_type") or "").lower()
                        jobkorea_id = item.get("jobkorea_posting_id")
                        landing_url = str(item.get("link") or item.get("landing_url") or "").lower()

                        if (
                            apply_type in ["jobkorea_inlink", "external_link"]
                            or jobkorea_id is not None
                            or "jobkorea.co.kr" in landing_url
                        ):
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

                        raw_deadline = item.get("deadline_message") or item.get("end_at") or ""
                        deadline = self._format_deadline(str(raw_deadline))

                        # 잡플래닛 정식 상세 URL 규격
                        job_url = f"https://www.jobplanet.co.kr/job/search?posting_ids%5B%5D={job_id}"

                        # 디버그 프린트
                        print(f"[잡플래닛 파싱] ID: {job_id} | 기업: {company} | 제목: {title} | 경력: '{req_exp}' | 마감일: '{deadline}'")

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

                    if len(jobs) >= 20:
                        break
                else:
                    print(f"[잡플래닛] API 응답 에러 (Status Code: {res.status_code})")
                    break

            except Exception as e:
                print(f"[잡플래닛] 수집 오류: {e}")
                break

        print(f"[잡플래닛] 수집 완료: 총 {len(jobs)}건 (잡코리아 연동 공고 제외됨)")
        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """잡플래닛 공고 상세 내용 조회"""
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