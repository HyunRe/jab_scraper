import pytest
from unittest.mock import MagicMock, patch
from app.presentation.notion_analysis_notifier import NotionAnalysisNotifier
from app.domain.models import Job, JobEvaluation


def test_save_company_analysis_structure():
    print("\n[TEST START] Notion Analysis DB 기업 및 직무 분석 저장 구조 검증 테스트 시작")
    try:
        mock_notion_client = MagicMock()

        with patch("app.presentation.notion_analysis_notifier.Client", return_value=mock_notion_client):
            fake_db_id = "fake_analysis_db_id"

            notifier = NotionAnalysisNotifier(
                notion_token="fake_token",
                analysis_db_id=fake_db_id
            )

            job = Job(
                id="123",
                platform="원티드",
                title="백엔드 엔지니어",
                company="카카오",
                url="https://example.com/job/123",
                location="판교",
                required_experience="3년 이상",
                deadline="상시"
            )

            evaluation = JobEvaluation(
                job=job,
                score="상",
                matched_domain="원티드 / BACKEND (V1)",
                match_or_lack_reason="Spring Boot 및 Redis 기술 스택 일치",
                matching_tech_stacks=["Java", "Spring Boot", "Redis"],
                customized_resume_summary_html="<div>이력서 요약</div>",
                customized_cover_letter_html="<div>자기소개서</div>"
            )

            mock_notion_client.pages.create.return_value = {"id": "new_analysis_page_id"}
            original_page_id = "page_12345"

            # 실제 구현 메서드인 save_evaluations 호출
            notifier.save_evaluations(
                evaluations=[evaluation],
                original_page_id=original_page_id
            )

            mock_notion_client.pages.create.assert_called_once()
            create_kwargs = mock_notion_client.pages.create.call_args[1]

            assert create_kwargs["parent"]["database_id"] == fake_db_id
            properties = create_kwargs["properties"]

            # 실제 클래스에 정의된 노션 속성명 및 도메인/적합도 검증
            assert "분석 내용 및 이력서 & 자소서 수정" in properties
            assert properties["분석 내용 및 이력서 & 자소서 수정"]["title"][0]["text"]["content"] == "[카카오] 백엔드 엔지니어"

            assert "적합도" in properties
            assert properties["적합도"]["select"]["name"] == "상"

            assert "도메인" in properties
            assert properties["도메인"]["rich_text"][0]["text"]["content"] == "원티드 / BACKEND (V1)"

            assert "공고 스크립트" in properties
            assert properties["공고 스크립트"]["relation"][0]["id"] == original_page_id

            # ⭕ [추가] 지원 컬럼 초기값('대기') 세팅 검증
            assert "지원" in properties
            assert properties["지원"]["select"]["name"] == "대기"

            mock_notion_client.blocks.children.append.assert_called_once()
            append_kwargs = mock_notion_client.blocks.children.append.call_args[1]
            assert append_kwargs["block_id"] == "new_analysis_page_id"

            print("  └ [OK] 기업 분석 정보 DB 저장 파라미터 검증 성공")
            print("✅ [TEST SUCCESS] Notion Analysis DB 저장 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] Notion Analysis DB 저장 검증 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e


def test_exists_by_original_page_id():
    print("\n[TEST START] Notion Analysis DB 중복 페이지 검사(exists_by_original_page_id) 테스트 시작")
    try:
        mock_notion_client = MagicMock()

        with patch("app.presentation.notion_analysis_notifier.Client", return_value=mock_notion_client):
            notifier = NotionAnalysisNotifier(
                notion_token="fake_token",
                analysis_db_id="fake_analysis_db_id"
            )

            # 1. 중복 데이터가 존재할 때 (True 반환 검증)
            mock_notion_client.databases.query.return_value = {
                "results": [{"id": "existing_analysis_page_id"}]
            }
            exists = notifier.exists_by_original_page_id("page_12345")

            assert exists is True
            mock_notion_client.databases.query.assert_called_once()
            query_kwargs = mock_notion_client.databases.query.call_args[1]
            assert query_kwargs["filter"]["property"] == "공고 스크립트"
            assert query_kwargs["filter"]["relation"]["contains"] == "page_12345"
            print("  └ [OK] 기존 페이지 존재 시 True 반환 검증 완료")

            # 2. 중복 데이터가 없을 때 (False 반환 검증)
            mock_notion_client.databases.query.return_value = {"results": []}
            not_exists = notifier.exists_by_original_page_id("page_67890")

            assert not_exists is False
            print("  └ [OK] 기존 페이지 없을 시 False 반환 검증 완료")

            print("✅ [TEST SUCCESS] exists_by_original_page_id 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] 중복 검사 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e


def test_get_completed_applications():
    print("\n[TEST START] Notion Analysis DB '지원 완료' 건 조회 메서드 테스트 시작")
    try:
        mock_notion_client = MagicMock()

        with patch("app.presentation.notion_analysis_notifier.Client", return_value=mock_notion_client):
            notifier = NotionAnalysisNotifier(
                notion_token="fake_token",
                analysis_db_id="fake_analysis_db_id"
            )

            mock_notion_client.databases.query.return_value = {
                "results": [
                    {
                        "id": "analysis_page_1",
                        "properties": {
                            "분석 내용 및 이력서 & 자소서 수정": {
                                "title": [{"text": {"content": "[카카오] 백엔드 개발자"}}]
                            }
                        }
                    }
                ]
            }

            results = notifier.get_completed_applications()

            assert len(results) == 1
            assert results[0]["id"] == "analysis_page_1"
            assert results[0]["company"] == "카카오"
            assert results[0]["job_title"] == "백엔드 개발자"

            # 쿼리 필터 파라미터 검증
            query_kwargs = mock_notion_client.databases.query.call_args[1]
            assert query_kwargs["filter"]["property"] == "지원"
            assert query_kwargs["filter"]["select"]["equals"] == "지원 완료"

            print("  └ [OK] '지원 완료' 필터링 쿼리 파라미터 및 결과 파싱 검증 완료")
            print("✅ [TEST SUCCESS] get_completed_applications 테스트 통과!\n")

    except AssertionError as e:
        print(f"❌ [TEST FAIL] '지원 완료' 건 조회 테스트 실패: {e}\n")
        raise e
    except Exception as e:
        print(f"💥 [TEST ERROR] 예외 발생: {e}\n")
        raise e