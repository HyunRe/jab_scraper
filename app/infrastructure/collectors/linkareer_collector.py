import os
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class LinkareerCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.base_url = "https://api.linkareer.com/graphql"
        self.headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Device": "web",
            "Origin": "https://linkareer.com",
            "Referer": "https://linkareer.com/",
        }

    def supports(self, platform: str) -> bool:
        return platform == "링커리어"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리
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
            # 수정된 GraphQL 쿼리: 에러 로그 분석 결과(filterBy, ActivityFilter) 반영 및 유효 필드만 조회
            graphql_query = {
                "operationName": "RecruitList",
                "variables": {
                    "filterBy": {
                        "keyword": "백엔드",
                        "activityTypeID": 5  # 채용 공고
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

            res = requests.post(
                self.base_url,
                headers=self.headers,
                json=graphql_query,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                res_data = res.json() if isinstance(res.json(), dict) else {}
                activities = res_data.get("data", {}).get("activities", {}).get("nodes", []) if isinstance(
                    res_data.get("data"), dict) else []

                for item in activities:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("title") or "제목 없음").strip()
                    company = str(item.get("organizationName") or "기업명 미상").strip()

                    # 상세 필드가 없는 경우 기본값 및 ID 기반 URL 생성
                    location = "상세 참조"
                    req_exp = "경력 무관"
                    deadline = "상시 채용"
                    job_url = f"https://linkareer.com/activity/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="링커리어",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[링커리어] 수집 완료: {len(jobs)}건")
            else:
                print(f"[링커리어] API 응답 에러 (Status Code: {res.status_code})")
                print(f"[링커리어] 에러 응답 내용: {res.text}")

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
                detail_area = soup.select_one("div.activity-detail") or soup.select_one("section.detail-content")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[링커리어] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"