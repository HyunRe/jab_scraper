import os
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class CatchCollector(JobCollectorRepository):
    def __init__(self, auth_token: str = None):
        self.auth_token = auth_token or os.getenv("CATCH_AUTH_TOKEN", "")
        self.base_url = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ko-KR,ko;q=0.9,en;q=0.8",
            "referer": "https://www.catch.co.kr/NCS/RecruitSearch",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "x-auth-token": self.auth_token,
            "x-is-pc": "true"
        }

    def supports(self, platform: str) -> bool:
        return platform == "캐치"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리 (사람인/원티드와 동일 패턴)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[캐치] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="캐치",
                    title="[CI Mock] 캐치 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.catch.co.kr/NCS/RecruitInfoDetail/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "Keyword": "백엔드",
                "JobCode": "",
                "Sido": "",
                "Career": "",
                "JCode": "",
                "Size": "",
                "EduLevel": "",
                "WorkPosition": "",
                "CompID": "",
                "GroupCode": "",
                "Sort": "0",
                "curpage": 1,
                "Priority": "",
                "pageSize": 30,
                "onRecruitYN": "Y",
                "ExceptIDList": ""
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                data = res.json() if isinstance(res.json(), dict) else {}
                recruit_list = data.get("recruitData", []) or []

                for item in recruit_list:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("RecruitID") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("RecruitTitle") or "제목 없음").strip()
                    company = str(item.get("CompName") or "기업명 미상").strip()
                    location = str(item.get("WorkArea") or "상세 참조").strip()

                    # 경력 조건 매핑
                    career_code = str(item.get("CareerGubunCode") or "")
                    req_exp = career_code if career_code else "경력 무관"

                    # 마감일 매핑
                    end_date = str(item.get("ApplyEndDatetime") or "").strip()
                    deadline = end_date.split("T")[0] if end_date and "9999" not in end_date else "상시 채용"

                    job_url = f"https://www.catch.co.kr/NCS/RecruitInfoDetail/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="캐치",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[캐치] 수집 완료: {len(jobs)}건")
            else:
                print(f"[캐치] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[캐치] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """캐치 공고 웹 페이지 HTML 파싱 기반 상세 내용 조회"""
        try:
            res = requests.get(
                job.url,
                headers={"User-Agent": self.headers["user-agent"]},
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = soup.select_one("div.re_view_box") or soup.select_one("div.tbl_detail")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[캐치] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"