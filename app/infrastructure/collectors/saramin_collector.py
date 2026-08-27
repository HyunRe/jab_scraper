import os
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class SaraminCollector(JobCollectorRepository):
    def __init__(self, saramin_api_key: str = None):
        self.saramin_api_key = saramin_api_key
        self.search_url = "https://www.saramin.co.kr/zf_user/search?searchword=%EB%B0%B1%EC%97%94%EB%93%9C+Spring"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.saramin.co.kr/",
        }

    def supports(self, platform: str) -> bool:
        return platform == "사람인"

    def fetch_jobs(self) -> List[Job]:
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[사람인] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="사람인",
                    title="[CI Mock] 사람인 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs = []
        try:
            print(f"\n================ [사람인 요청 디버그] ================")
            print(f"Request URL: {self.search_url}")
            print(f"Request Headers: {self.headers}")

            res = requests.get(
                self.search_url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )

            print(f"Response Status Code: {res.status_code}")
            print(f"Response Headers: {dict(res.headers)}")

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                job_items = soup.select("div.item_rec, div.item_recruit, div.list_item")

                for item in job_items:
                    # 1. 제목 및 URL 방어 로직
                    title_anchor = item.select_one("h2.job_tit a, div.job_tit a, a.bl_title")
                    if not title_anchor:
                        continue

                    title = title_anchor.get_text(strip=True) or "제목 없음"
                    rel_url = str(title_anchor.get("href") or "")
                    if not rel_url:
                        continue

                    job_url = f"https://www.saramin.co.kr{rel_url}" if rel_url.startswith("/") else rel_url

                    # rec_idx 추출 방어
                    job_id = "0"
                    if "rec_idx=" in rel_url:
                        try:
                            job_id = rel_url.split("rec_idx=")[1].split("&")[0]
                        except IndexError:
                            job_id = "0"

                    # 2. 기업명 방어 로직
                    company_anchor = item.select_one("div.area_corp a.corp_name")
                    company = company_anchor.get_text(strip=True) if company_anchor else "기업명 미상"

                    # 3. 조건 정보 (지역, 경력) 방어 로직
                    conditions = [s.get_text(strip=True) for s in item.select("div.job_condition span") if s.get_text(strip=True)]
                    location = conditions[0] if len(conditions) > 0 else "상세 참조"
                    experience = conditions[1] if len(conditions) > 1 else "경력 무관"

                    # 4. 마감일 방어 로직
                    date_span = item.select_one("span.date")
                    deadline = date_span.get_text(strip=True) if date_span else "상시 채용"

                    jobs.append(Job(
                        id=job_id,
                        platform="사람인",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=experience,
                        deadline=deadline
                    ))

                print(f"[사람인] 크롤링 수집 완료: {len(jobs)}건")

                if len(jobs) == 0:
                    with open("saramin_empty_200.html", "w", encoding="utf-8") as f:
                        f.write(res.text)
                    print("⚠️ [사람인] 수집된 공고가 0건입니다. 'saramin_empty_200.html'에 응답 HTML이 저장되었습니다.")

            else:
                print(f"[사람인] 크롤링 응답 에러 (Status Code: {res.status_code})")
                with open("saramin_error_403.html", "w", encoding="utf-8") as f:
                    f.write(res.text)
                print("⚠️ [사람인] 에러 응답 본문이 'saramin_error_403.html'에 저장되었습니다.")
        except Exception as e:
            print(f"[사람인] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        return f"""
        [근무위치]: {job.location}
        [요구경력]: {job.required_experience}
        [마감일자]: {job.deadline}
        [상세안내]: 사람인 공고의 상세 정보는 아래 지원 링크(URL)를 참고해 주세요.
        """