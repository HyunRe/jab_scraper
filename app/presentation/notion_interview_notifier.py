from notion_client import Client
from typing import List, Dict, Any


class NotionInterviewNotifier:
    def __init__(self, notion_token: str, interview_db_id: str):
        self.notion_token = notion_token
        self.notion = Client(auth=notion_token)
        self.interview_db_id = interview_db_id

    def _chunk_text(self, text: str, limit: int = 2000) -> List[dict]:
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
        return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]

    def fetch_existing_interview_prep_page_ids(self) -> List[str]:
        """DB 3(면접 준비)에 이미 연결된 DB 2의 페이지 ID 목록 추출"""
        if not self.interview_db_id:
            return []
        try:
            if hasattr(self.notion, "databases") and hasattr(self.notion.databases, "query"):
                response = self.notion.databases.query(database_id=self.interview_db_id)
            else:
                import requests
                headers = {
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.interview_db_id}/query",
                    headers=headers,
                    json={}
                )
                response = res.json()

            linked_ids = []
            for page in response.get("results", []):
                relations = page.get("properties", {}).get("분석 스크립트", {}).get("relation", [])
                for rel in relations:
                    linked_ids.append(rel["id"])
            return linked_ids
        except Exception as e:
            print(f"[Notion DB 3] 기존 내역 조회 오류: {e}")
            return []

    def save_interview_prep(self, company: str, job_title: str, prep_data: Any, original_page_id: str):
        """DB 3(면접/코테 준비)에 질문 및 답변 가이드를 토글 형식으로 저장 후 DB 2와 관계형 연결"""
        if not self.interview_db_id:
            raise ValueError("DB 3 (Interview Database ID)가 설정되지 않았습니다.")

        try:
            title_content = f"[{company}] {job_title}" if company and company not in job_title else job_title

            new_page = self.notion.pages.create(
                parent={"database_id": self.interview_db_id},
                properties={
                    "예상 질문 & 코테 준비": {
                        "title": [{"text": {"content": title_content}}]
                    },
                    "분석 스크립트": {
                        "relation": [{"id": original_page_id}]
                    },
                    "진행 상태": {
                        "select": {"name": "서류 제출 완료"}
                    }
                }
            )

            page_id = new_page["id"]
            # 타입 힌트 명시 (PyCharm 타입 경고 제거)
            children_blocks: List[Dict[str, Any]] = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💡 심화 기술 면접 예상 질문 & 핵심 답변 가이드"}}]}
                }
            ]

            # 토글(Toggle) 형태로 질문 및 하위 답변 구조 배치
            for idx, item in enumerate(prep_data.interview_questions, 1):
                # Pydantic 모델과 dict 모두 대응 가능한 안전한 데이터 추출 방식
                if hasattr(item, "model_dump"):
                    data = item.model_dump()
                elif isinstance(item, dict):
                    data = item
                else:
                    data = {
                        "question": getattr(item, "question", ""),
                        "summary": getattr(item, "summary", ""),
                        "keywords": getattr(item, "keywords", []),
                        "experience_point": getattr(item, "experience_point", "")
                    }

                q_text = data.get("question", "")
                summary = data.get("summary", "")
                keywords = data.get("keywords", [])
                exp_point = data.get("experience_point", "")

                keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

                toggle_block = {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": f"{idx}. {q_text}"}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {
                                    "rich_text": [
                                        {"type": "text", "text": {"content": "핵심 요약: "}, "annotations": {"bold": True}},
                                        {"type": "text", "text": {"content": summary}}
                                    ]
                                }
                            },
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {
                                    "rich_text": [
                                        {"type": "text", "text": {"content": "필수 키워드: "},
                                         "annotations": {"bold": True}},
                                        {"type": "text", "text": {"content": keywords_str}}
                                    ]
                                }
                            },
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {
                                    "rich_text": [
                                        {"type": "text", "text": {"content": "경험 연계 포인트: "},
                                         "annotations": {"bold": True}},
                                        {"type": "text", "text": {"content": exp_point}}
                                    ]
                                }
                            }
                        ]
                    }
                }
                children_blocks.append(toggle_block)

            children_blocks.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💻 맞춤 코딩 테스트 & SQL 준비 지침"}}]}
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": self._chunk_text(prep_data.coding_test_prep)}
                }
            ])

            self.notion.blocks.children.append(block_id=page_id, children=children_blocks)
            print(f"[Notion DB 3] 면접/코테 준비 데이터 저장 완료: '{title_content}'")

        except Exception as e:
            print(f"[Notion DB 3] 저장 오류 ({job_title}): {e}")
            raise e