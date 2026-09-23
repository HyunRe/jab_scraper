import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class InthisworkCollector(JobCollectorRepository):
    def __init__(self, cookies: Optional[dict] = None):
        # 신입/인턴, 주니어/경력, IT직무 페이지를 모두 수집 대상에 포함
        self.target_urls = [
            "https://inthiswork.com/entry",
            "https://inthiswork.com/junior",
            "https://inthiswork.com/it",
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://inthiswork.com/",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.cookies = cookies or {}

    def supports(self, platform: str) -> bool:
        return platform in ["인디스워크", "INTHISWORK"]

    def _resolve_experience_level(self, raw_category: str, title: str, source_url: str) -> str:
        categories = raw_category.split() if raw_category else []

        has_entry_cat = any("신입" in cat or "인턴" in cat for cat in categories)
        has_junior_cat = any("주니어" in cat or "경력" in cat for cat in categories)

        if "/entry" in source_url:
            has_entry_cat = True
        elif "/junior" in source_url:
            has_junior_cat = True

        title_lower = title.lower()
        if any(kw in title_lower for kw in ["경력 무관", "경력무관", "신입/경력", "신입 / 경력", "경력/신입"]):
            has_entry_cat = True
            has_junior_cat = True

        if has_entry_cat and has_junior_cat:
            return "신입/경력 (무관)"
        elif has_entry_cat:
            return "신입/인턴"
        elif has_junior_cat:
            return "주니어경력"

        return "경력미상"

    def _format_deadline(self, deadline_str: str) -> str:
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        now = datetime.now()

        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        elif "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned, re.IGNORECASE)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        if any(keyword in cleaned for keyword in ["전", "시간 전", "분 전", "일 전", "상시", "채용시", "채용 시"]):
            return "상시 채용"

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
        if os.getenv("GITHUB_ACTIONS") == "true":
            return [
                Job(
                    id="mock_inthiswork_1",
                    platform="인디스워크",
                    title="[CI Mock] 백엔드 개발자",
                    company="테스트 기업",
                    url="https://inthiswork.com/archives/mock_1",
                    location="서울",
                    required_experience="신입/경력 (무관)",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        visited_urls = set()
        keywords = ["백엔드", "backend", "server", "java", "spring", "서버", "개발", "it개발"]

        for target_url in self.target_urls:
            try:
                res = requests.get(
                    target_url,
                    headers=self.headers,
                    cookies=self.cookies,
                    impersonate="chrome120",
                    timeout=10
                )

                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    entries = soup.select("div.dpt-entry")

                    for entry in entries:
                        link_el = entry.select_one("a.dpt-title-link, a.dpt-permalink")

                        job_url = ""
                        if link_el and "href" in link_el.attrs:
                            job_url = str(link_el["href"])

                        # URL 중복 제거
                        if not job_url or job_url in visited_urls:
                            continue

                        raw_title = str(entry.get("data-title") or "").strip()
                        if not raw_title and link_el:
                            raw_title = link_el.get_text(strip=True)

                        company = "인디스워크 공고"
                        title = raw_title

                        if "｜" in raw_title:
                            company, title = map(str.strip, raw_title.split("｜", 1))
                        elif "|" in raw_title:
                            company, title = map(str.strip, raw_title.split("|", 1))

                        post_tags = str(entry.get("data-post_tag") or "").lower()
                        full_search_text = f"{title.lower()} {post_tags}"

                        # 키워드 필터링
                        if not any(kw in full_search_text for kw in keywords):
                            continue

                        visited_urls.add(job_url)

                        post_id = entry.get("data-id")
                        job_id = f"inthiswork_{post_id}" if post_id else f"inthiswork_{hash(job_url)}"

                        raw_category = str(entry.get("data-category") or "")
                        experience_level = self._resolve_experience_level(raw_category, title, target_url)

                        deadline_str = "상시 채용" if "채용시마감" in post_tags else "기한있음"

                        jobs.append(
                            Job(
                                id=job_id,
                                platform="인디스워크",
                                title=title,
                                company=company,
                                url=job_url,
                                location="서울/수도권",
                                required_experience=experience_level,
                                deadline=self._format_deadline(deadline_str),
                            )
                        )
                else:
                    # 응답 에러 발생 시 로그 출력
                    print(f"[인디스워크] API 응답 에러 ({target_url}) (Status Code: {res.status_code})")

            except Exception as e:
                print(f"[인디스워크] 수집 오류 ({target_url}): {e}")

        print(f"[인디스워크] 총 {len(jobs)}건 수집 완료")
        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """
        인디스워크 공고 상세 내용 조회:
        1. 상세 페이지 HTML 요청 후 텍스트 파싱 시도 (텍스트 공고 대응)
        2. 본문 텍스트가 없거나 파싱 실패 시 기본 메타데이터 반환 (이미지 공고 대응)
        """
        fallback_text = (
            f"직무명: {job.title} / 회사명: {job.company} / "
            f"위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"
        )

        # 1. Mock 데이터인 경우 즉시 Fallback 반환
        if "mock" in job.id:
            return f"[{job.title}] (CI Mock 상세 정보) - {fallback_text}"

        try:
            # 2. 캐치/인크루트와 동일하게 상세 페이지 HTML 파싱 시도
            res = requests.get(
                job.url,
                headers=self.headers,
                cookies=self.cookies,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")

                # 인디스워크 게시글 본문 영역 셀렉터 (WordPress 표준 entry-content 또는 dpt-content)
                detail_area = (
                        soup.select_one("div.dpt-content")
                        or soup.select_one("div.entry-content")
                        or soup.select_one("article")
                )

                if detail_area:
                    # 이미지 태그, 스크립트 등 불필요 요소 제거
                    for unwanted in detail_area.select("script, style, iframe, img"):
                        unwanted.decompose()

                    content_text = detail_area.get_text(separator="\n", strip=True)

                    # 3. 파싱된 본문 텍스트가 의미 있는 수준(10자 이상)으로 존재하는 경우
                    if len(content_text) >= 10:
                        return f"[{job.title}] 상세 정보:\n{content_text[:1200]}"

        except Exception as e:
            print(f"[인디스워크] 상세 정보 조회 오류 ({job.id}): {e}")

        # 4. 이미지 전용 공고이거나 HTML 파싱 실패 시 기본 메타데이터 반환
        return f"[{job.title}] (이미지/기본 정보 공고):\n{fallback_text}"