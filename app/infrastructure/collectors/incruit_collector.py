import os
from datetime import datetime
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class IncruitCollector(JobCollectorRepository):
    def __init__(self, cookies: dict = None):
        self.base_url = "https://job.incruit.com/jobdb_list/searchjob.asp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://job.incruit.com/",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.cookies = cookies or {}

    def supports(self, platform: str) -> bool:
        return platform == "인크루트"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 형식으로 파싱 및 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()

        # 상대 시간 표현(예: '3일 전', '2시간 전')이나 불필요한 문구 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return ""

        if "상시" in cleaned or "채용시" in cleaned or "채용 시" in cleaned or "9999" in cleaned:
            return "상시 채용"

        try:
            # 연도가 포함된 형식 (예: 2026-04-15, 2026.04.15)
            match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                weekdays = ['월', '화', '수', '목', '금', '토', '일']
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일 형식 또는 날짜 형태 (예: 04/15, 4월 15일)
            match_md = re.search(r'(\d{1,2})[./월]\s*(\d{1,2})일?', cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                current_year = datetime.now().year
                dt = datetime(current_year, month, day)
                weekdays = ['월', '화', '수', '목', '금', '토', '일']
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리 (사람인/원티드/캐치와 동일 패턴)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[인크루트] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="인크루트",
                    title="[CI Mock] 인크루트 백엔드 개발자",
                    company="테스트 기업",
                    url="https://job.incruit.com/jobdb_info/jobpost.asp?job=mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            # ct=3, ty=2, cd=11 기본 설정 및 검색어 대응
            params = {
                "kw": "백엔드",
                "ct": 3,
                "ty": 2,
                "cd": 11,
                "page": 1
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                # 인크루트 인코딩 대응 (euc-kr -> utf-8)
                res.encoding = "euc-kr"
                soup = BeautifulSoup(res.text, "html.parser")
                job_rows = soup.select("ul.c_row")

                for item in job_rows:
                    title_elem = item.select_one("div.cell_mid div.cl_top > a")
                    if not title_elem:
                        continue

                    title = title_elem.text.strip() or "제목 없음"
                    job_url = str(title_elem.get("href") or "").strip()
                    if not job_url:
                        continue

                    # jobno 추출 및 job_id 세팅
                    job_id = str(item.get("jobno") or "").strip()
                    if not job_id and "job=" in job_url:
                        try:
                            job_id = job_url.split("job=")[1].split("&")[0]
                        except IndexError:
                            job_id = "0"

                    company_elem = item.select_one("div.cell_first a.cpname")
                    company = company_elem.text.strip() if company_elem else "기업명 미상"

                    # 조건 정보 (지역, 경력) 추출
                    cond_spans = [s.text.strip() for s in item.select("div.cell_mid div.cl_md > span") if
                                  s.text.strip()]
                    location = cond_spans[0] if len(cond_spans) > 0 else "상세 참조"
                    experience = cond_spans[1] if len(cond_spans) > 1 else "경력 무관"

                    # 마감일 추출 및 포맷 통일 적용
                    deadline_elem = item.select_one("div.cell_last div.cl_btm > span:nth-of-type(1)")
                    raw_deadline = deadline_elem.text.strip() if deadline_elem else ""
                    deadline = self._format_deadline(raw_deadline)

                    jobs.append(Job(
                        id=job_id or "0",
                        platform="인크루트",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=experience,
                        deadline=deadline
                    ))

                print(f"[인크루트] 크롤링 수집 완료: {len(jobs)}건")
            else:
                print(f"[인크루트] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[인크루트] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """인크루트 공고 상세 페이지 파싱"""
        try:
            res = requests.get(
                job.url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                res.encoding = "euc-kr"
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = soup.select_one("div.section_detail_view") or soup.select_one("div.jc_detail")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[인크루트] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"