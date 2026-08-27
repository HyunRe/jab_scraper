from datetime import datetime
from notion_client import Client
from typing import List, Dict, Any, Optional
from app.domain.models import JobEvaluation


class NotionAnalysisNotifier:
    def __init__(self, notion_token: str, analysis_db_id: str):
        self.notion_token = notion_token
        self.notion = Client(auth=notion_token)
        self.analysis_db_id = analysis_db_id

    def _chunk_text(self, text: str, limit: int = 2000) -> List[dict]:
        """노션 API의 2000자 제한을 회피하기 위해 text를 조각내어 rich_text 구조 배열로 반환"""
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
        return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]

    def exists_by_original_page_id(self, original_page_id: str) -> bool:
        """
        DB 2(공고 분석)에 이미 해당 DB 1 공고(original_page_id)에 대한
        분석 결과 페이지가 만들어져 있는지 중복 여부를 확인합니다.
        """
        if not self.analysis_db_id or not original_page_id:
            return False

        try:
            filter_query = {
                "property": "공고 스크립트",
                "relation": {
                    "contains": original_page_id
                }
            }

            if hasattr(self.notion, "databases") and hasattr(self.notion.databases, "query"):
                response = self.notion.databases.query(
                    database_id=self.analysis_db_id,
                    filter=filter_query
                )
            else:
                import requests
                headers = {
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.analysis_db_id}/query",
                    headers=headers,
                    json={"filter": filter_query}
                )
                response = res.json()

            results = response.get("results", [])
            return len(results) > 0

        except Exception as e:
            print(f"[Notion DB 2] 중복 확인 중 오류 발생 ({original_page_id}): {e}")
            return False

    def save_evaluations(self, evaluations: List[JobEvaluation], original_page_id: Optional[str] = None):
        """
        Gemini LLM의 분석 결과 및 자소서 각색 내용(HTML)을
        DB 2(공고 분석)에 저장하고 DB 1과 관계형(Relation) 링크 매핑
        """
        if not self.analysis_db_id:
            raise ValueError("DB 2 (Analysis Database ID)가 설정되지 않았습니다.")

        for eval_item in evaluations:
            try:
                title_text = f"[{eval_item.job.company}] {eval_item.job.title}"

                # 노션 실제 DB 스키마([분석 내용 및 이력서 & 자소서 수정], [공고 스크립트], [도메인], [적합도], [지원])에 맞춤
                properties: Dict[str, Any] = {
                    "분석 내용 및 이력서 & 자소서 수정": {
                        "title": [{"text": {"content": title_text}}]
                    },
                    "적합도": {
                        "select": {"name": eval_item.score}
                    },
                    "도메인": {
                        "rich_text": [{"text": {"content": eval_item.matched_domain}}]
                    },
                    "지원": {
                        "select": {"name": "대기"}
                    }
                }

                # 1단계(공고 스크립트) 페이지 ID가 있다면 노션 relation 속성 추가
                target_page_id = original_page_id or getattr(eval_item.job, "page_id", None)
                if target_page_id:
                    properties["공고 스크립트"] = {
                        "relation": [{"id": str(target_page_id)}]
                    }

                # 노션 DB 2 페이지 생성
                new_page = self.notion.pages.create(
                    parent={"database_id": self.analysis_db_id},
                    properties=properties
                )

                page_id = new_page["id"]
                tech_stack_str = ", ".join(eval_item.matching_tech_stacks) if eval_item.matching_tech_stacks else "없음"

                # 본문 블록 구성
                children_blocks = [
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📌 적합성 및 부족한 점"}}]}
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": self._chunk_text(eval_item.match_or_lack_reason)}
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🛠 일치하는 주요 기술 스택"}}]}
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": tech_stack_str}}]}
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "✏️ 핵심 기술 요약 (이력서)"}}]}
                    },
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "caption": [],
                            "rich_text": self._chunk_text(eval_item.customized_resume_summary_html),
                            "language": "html"
                        }
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "📄 각색된 자소서 전체 (블루/레드 마킹 적용)"}}]}
                    },
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "caption": [],
                            "rich_text": self._chunk_text(eval_item.customized_cover_letter_html),
                            "language": "html"
                        }
                    }
                ]

                self.notion.blocks.children.append(block_id=page_id, children=children_blocks)
                print(f"[Notion DB 2] 분석 및 각색 결과 저장 완료: '{title_text}'")

            except Exception as e:
                print(f"[Notion DB 2] 저장 오류 ({eval_item.job.title}): {e}")

    def fetch_applied_jobs(self) -> List[Dict[str, Any]]:
        """DB 2에서 사용자가 '지원' 상태를 '지원 완료'로 변경한 공고 목록 조회"""
        try:
            if hasattr(self.notion, "databases") and hasattr(self.notion.databases, "query"):
                response = self.notion.databases.query(
                    database_id=self.analysis_db_id,
                    filter={
                        "property": "지원",
                        "select": {
                            "equals": "지원 완료"
                        }
                    }
                )
            else:
                import requests
                headers = {
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                payload = {
                    "filter": {
                        "property": "지원",
                        "select": {
                            "equals": "지원 완료"
                        }
                    }
                }
                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.analysis_db_id}/query",
                    headers=headers,
                    json=payload
                )
                response = res.json()

            applied_jobs = []
            for page in response.get("results", []):
                props = page.get("properties", {})
                title_text = props.get("분석 내용 및 이력서 & 자소서 수정", {}).get("title", [{}])[0].get("text", {}).get("content", "")

                # "[회사명] 공고명" 형태에서 회사명 파싱
                company = ""
                if title_text.startswith("[") and "]" in title_text:
                    company = title_text.split("]")[0].replace("[", "").strip()

                applied_jobs.append({
                    "page_id": page["id"],
                    "title_text": title_text,
                    "company": company
                })
            return applied_jobs
        except Exception as e:
            print(f"[Notion DB 2] 지원 완료 공고 조회 오류: {e}")
            return []

    def get_completed_applications(self) -> List[Dict[str, Any]]:
        """테스트 및 외부 호출용: 지원 상태가 '지원 완료'인 페이지들을 조회합니다."""
        try:
            if hasattr(self.notion, "databases") and hasattr(self.notion.databases, "query"):
                response = self.notion.databases.query(
                    database_id=self.analysis_db_id,
                    filter={
                        "property": "지원",
                        "select": {
                            "equals": "지원 완료"
                        }
                    }
                )
            else:
                import requests
                headers = {
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                payload = {
                    "filter": {
                        "property": "지원",
                        "select": {
                            "equals": "지원 완료"
                        }
                    }
                }
                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.analysis_db_id}/query",
                    headers=headers,
                    json=payload
                )
                response = res.json()

            completed_list = []
            for page in response.get("results", []):
                page_id = page["id"]
                props = page.get("properties", {})
                title_list = props.get("분석 내용 및 이력서 & 자소서 수정", {}).get("title", [])
                full_title = title_list[0].get("text", {}).get("content", "") if title_list else ""

                # [회사명] 공고명 포맷 파싱
                company, job_title = "", full_title
                if full_title.startswith("[") and "]" in full_title:
                    parts = full_title.split("]", 1)
                    company = parts[0].replace("[", "").strip()
                    job_title = parts[1].strip()

                completed_list.append({
                    "id": page_id,
                    "company": company,
                    "job_title": job_title
                })

            return completed_list
        except Exception as e:
            print(f"[Notion DB 2] get_completed_applications 조회 오류: {e}")
            return []