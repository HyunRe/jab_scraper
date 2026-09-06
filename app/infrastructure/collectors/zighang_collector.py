import os
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class ZighangCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.base_url = "https://api.zighang.com/api/recruitments"
        self.headers = headers or {
            "accept": "application/json",
            "accept-language": "ko-KR,ko;q=0.9,en;q=0.8,en-US;q=0.7",
            "origin": "https://zighang.com",
            "referer": "https://zighang.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        }

    def supports(self, platform: str) -> bool:
        return platform == "직행"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리 (타 수집기들과 동일 패턴)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[직행] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="직행",
                    title="[CI Mock] 직행 백엔드 개발자",
                    company="테스트 기업",
                    url="https://zighang.com/recruitment/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "page": 0,
                "size": 30,
                "depthTwos": "서버_백엔드",
                "includeCareerOpen": "true",
                "sortCondition": "ZIGHANG_SCORE",
                "orderCondition": "DESC"
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                res_data = res.json() if isinstance(res.json(), dict) else {}
                payload = res_data.get("data", {}) if isinstance(res_data.get("data"), dict) else {}
                content = payload.get("content", []) if isinstance(payload.get("content"), list) else []

                for item in content:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("title") or item.get("recruitmentTitle") or "제목 없음").strip()

                    company_info = item.get("company") or item.get("companyName") or {}
                    if isinstance(company_info, dict):
                        company = str(company_info.get("name") or "기업명 미상").strip()
                    else:
                        company = str(company_info).strip() or "기업명 미상"

                    location = str(item.get("address") or item.get("location") or "상세 참조").strip()

                    # 경력 매핑
                    career_text = item.get("career") or item.get("experience")
                    req_exp = str(career_text).strip() if career_text else "경력 무관"

                    # 마감일 매핑
                    deadline_msg = item.get("deadline") or item.get("dueDate")
                    deadline = str(deadline_msg).strip() if deadline_msg else "상시 채용"

                    job_url = f"https://zighang.com/recruitment/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="직행",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[직행] 수집 완료: {len(jobs)}건")
            else:
                print(f"[직행] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[직행] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """직행 공고 상세 정보 조회"""
        try:
            detail_url = f"https://api.zighang.com/api/recruitments/{job.id}"
            res = requests.get(
                detail_url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                d = res.json().get("data", {}) if isinstance(res.json(), dict) else {}
                description = d.get("description") or d.get("content") or ""
                return f"[{job.title}] 상세 정보:\n{description[:1000]}"
        except Exception as e:
            print(f"[직행] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"