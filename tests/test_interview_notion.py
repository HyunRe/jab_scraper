import pytest
from unittest.mock import MagicMock, patch
from app.presentation.notion_interview_notifier import NotionInterviewNotifier
from app.infrastructure.interview_preparer import InterviewPrepSchema, InterviewQuestionItem


def test_save_interview_prep_structure():
    print("\n[TEST START] Notion Interview DB 면접 준비 저장 구조 검증 테스트 시작")
    try:
        mock_notion_client = MagicMock()

        with patch("app.presentation.notion_interview_notifier.Client", return_value=mock_notion_client):
            fake_db_id = "fake_interview_db_id"

            notifier = NotionInterviewNotifier(
                notion_token="fake_token",
                interview_db_id=fake_db_id
            )

            company = "카카오"
            job_title = "백엔드 엔지니어"
            original_page_id = "page_12345"

            prep_data = InterviewPrepSchema(
                interview_questions=[
                    InterviewQuestionItem(
                        question="Redis TTL 설정 시 메모리 파편화 문제는 어떻게 방지하셨나요?",
                        summary="Active/Passive 만료 정책 및 maxmemory-policy 설정을 통해 메모리를 관리했습니다.",
                        keywords=["Active Expiration", "maxmemory-policy", "volatile-lru"],
                        experience_point="온복 프로젝트 레디스 캐시 만료 전략 적용 경험 언급"
                    ),
                    InterviewQuestionItem(
                        question="QueryDSL FetchJoin 사용 시 N+1 문제 해결 사례를 설명해 주세요.",
                        summary="FetchJoin과 BatchSize를 조합하여 1:N 관계의 N+1 문제를 방지하고 조회 성능을 개선했습니다.",
                        keywords=["FetchJoin", "BatchSize", "Cartesian Product"],
                        experience_point="TOTY 프로젝트 게시글 리스트 조회 쿼리 튜닝 경험 연계"
                    )
                ],
                coding_test_prep="Graph(BFS) 문제와 Group By / Join 기반 SQL 튜닝 연습을 권장합니다."
            )

            mock_notion_client.pages.create.return_value = {"id": "new_interview_page_id"}

            notifier.save_interview_prep(
                company=company,
                job_title=job_title,
                prep_data=prep_data,
                original_page_id=original_page_id
            )

            mock_notion_client.pages.create.assert_called_once()
            create_kwargs = mock_notion_client.pages.create.call_args[1]

            assert create_kwargs["parent"]["database_id"] == fake_db_id
            properties = create_kwargs["properties"]

            assert "예상 질문 & 코테 준비" in properties
            assert properties["예상 질문 & 코테 준비"]["title"][0]["text"]["content"] == f"[{company}] {job_title}"

            assert "분석 스크립트" in properties
            assert properties["분석 스크립트"]["relation"][0]["id"] == original_page_id

            mock_notion_client.blocks.children.append.assert_called_once()
            append_kwargs = mock_notion_client.blocks.children.append.call_args[1]

            assert append_kwargs["block_id"] == "new_interview_page_id"
            children = append_kwargs["children"]
            assert len(children) > 0

            toggle_blocks = [b for b in children if b.get("type") == "toggle"]
            assert len(toggle_blocks) == 2

            first_toggle = toggle_blocks[0]["toggle"]
            assert "1. Redis TTL 설정 시 메모리 파편화 문제는 어떻게 방지하셨나요?" in first_toggle["rich_text"][0]["text"]["content"]

            assert len(first_toggle["children"]) == 3
            # rich_text element 수준의 annotations 및 text.content 검증
            assert first_toggle["children"][0]["bulleted_list_item"]["rich_text"][0]["annotations"]["bold"] is True
            assert first_toggle["children"][0]["bulleted_list_item"]["rich_text"][1]["text"][
                       "content"] == "Active/Passive 만료 정책 및 maxmemory-policy 설정을 통해 메모리를 관리했습니다."

            print("  └ [OK] 토글 구조 및 하위 답변 키워드 자식 블록 파라미터 검증 성공")
            print("✅ [TEST SUCCESS] 노션 면접 준비 저장 구조 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] 노션 저장 구조 검증 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e