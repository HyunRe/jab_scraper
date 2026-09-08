import os
from datetime import datetime, timedelta
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository

# 백엔드 및 IT/개발 관련 키워드
_BACKEND_KEYWORDS = [
    "백엔드", "backend", "서버", "server", "java", "spring",
    "node", "python", "django", "flask", "go", "golang",
    "api", "개발", "개발자", "engineer", "developer", "software", "sw", "it"
]


class LinkareerCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.base_url = "https://api.linkareer.com/graphql"
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Device": "web",
            "Origin": "https://linkareer.com",
            "Referer": "https://linkareer.com/",
        }

    def supports(self, platform: str) -> bool:
        return platform == "링커리어"

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

    def _is_backend_related(self, title: str) -> bool:
        """공고 제목 기반 관련 여부 판단"""
        title_lower = title.lower()
        return any(kw in title_lower for kw in _BACKEND_KEYWORDS)

    def _build_query(self, activity_type_id: int = 5) -> dict:
        """
        GraphQL 쿼리 빌드.
        - filterBy 인자만 사용 (page, limit 완정 제거)
        - industryCategoryIDs: [5] (IT/SW 공고)
        """
        return {
            "operationName": "RecruitList",
            "variables": {
                "filterBy": {
                    "activityTypeID": activity_type_id,
                    "industryCategoryIDs": [5]
                }
            },
            "query": """
            query RecruitList($filterBy: ActivityFilter) {
              activities(filterBy: $filterBy) {
                nodes {
                  id
                  title
                  organizationName
                }
              }
            }
            """
        }

    def fetch_jobs(self) -> List[Job]:
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[링커리어] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="링커리어",
                    title="[CI Mock] 링커리어 백엔드 개발자",
                    company="테스트 기업",
                    url="https://linkareer.com/activity/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            res = requests.post(
                self.base_url,
                headers=self.headers,
                json=self._build_query(),
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code != 200:
                print(f"[링커리어] API 응답 에러 (Status Code: {res.status_code})")
                print(f"[링커리어] 에러 응답 내용: {res.text}")
                return jobs

            res_data = res.json() if isinstance(res.json(), dict) else {}

            if "errors" in res_data:
                for err in res_data["errors"]:
                    print(f"[링커리어] GraphQL 에러: {err.get('message')}")
                return jobs

            activities = (
                res_data
                .get("data", {})
                .get("activities", {})
                .get("nodes", [])
            )
            if not isinstance(activities, list):
                activities = []

            skipped = 0
            for item in activities:
                if not isinstance(item, dict):
                    continue

                job_id = str(item.get("id") or "").strip()
                if not job_id:
                    continue

                title = str(item.get("title") or "제목 없음").strip()

                if not self._is_backend_related(title):
                    skipped += 1
                    continue

                company = str(item.get("organizationName") or "기업명 미상").strip()
                deadline = self._format_deadline("")

                jobs.append(Job(
                    id=job_id,
                    platform="링커리어",
                    title=title,
                    company=company,
                    url=f"https://linkareer.com/activity/{job_id}",
                    location="상세 참조",
                    required_experience="경력 무관",
                    deadline=deadline
                ))

            print(f"[링커리어] 수집 완료: {len(jobs)}건 (필터 제외: {skipped}건)")

        except Exception as e:
            print(f"[링커리어] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """링커리어 공고 상세 정보 조회"""
        try:
            res = requests.get(
                job.url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = (
                    soup.select_one("div.activity-detail")
                    or soup.select_one("section.detail-content")
                )
                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[링커리어] 상세 정보 조회 오류 ({job.id}): {e}")

        return (
            f"직무명: {job.title} / 회사명: {job.company} / "
            f"위치: {job.location} / 경력: {job.required_experience} / "
            f"마감일: {job.deadline}"
        )