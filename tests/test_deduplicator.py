import base64
import json
from unittest.mock import MagicMock, patch
import pytest

from app.infrastructure.deduplicator import JobDeduplicator


@pytest.fixture
def sample_jobs():
    return [
        {"id": "wanted_1001", "title": "백엔드 개발자"},
        {"id": "wanted_1002", "title": "프론트엔드 개발자"},
        {"id": "saramin_2001", "title": "DevOps 엔지니어"}
    ]


@patch("requests.get")
def test_filter_new_jobs_with_existing_ids(mock_get, sample_jobs):
    print("\n[TEST START] Deduplicator - 기존 중복 ID 제외 필터링 테스트")
    try:
        existing_ids = ["wanted_1001"]
        encoded_content = base64.b64encode(json.dumps(existing_ids).encode("utf-8")).decode("utf-8")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": encoded_content,
            "sha": "mock_sha_12345"
        }
        mock_get.return_value = mock_response

        deduplicator = JobDeduplicator(repo_slug="user/repo", github_token="mock_token")
        new_jobs = deduplicator.filter_new_jobs(sample_jobs)

        assert len(new_jobs) == 2, f"신규 공고 개수 오류: expected 2, got {len(new_jobs)}"
        assert [job["id"] for job in new_jobs] == ["wanted_1002", "saramin_2001"]
        assert deduplicator.file_sha == "mock_sha_12345"

        print("  └ [OK] 중복 ID 제외 필터링 및 SHA 저장 성공")
        print("✅ [TEST SUCCESS] 기존 중복 ID 필터링 테스트 통과!\n")
    except AssertionError as e:
        print(f"❌ [TEST FAIL] 중복 ID 필터링 테스트 실패: {e}\n")
        raise e


@patch("requests.get")
def test_filter_new_jobs_when_file_not_found(mock_get, sample_jobs):
    print("\n[TEST START] Deduplicator - 신규 파일 생성 시 전체 수집 테스트")
    try:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        deduplicator = JobDeduplicator(repo_slug="user/repo", github_token="mock_token")
        new_jobs = deduplicator.filter_new_jobs(sample_jobs)

        assert len(new_jobs) == 3, f"신규 공고 개수 오류: expected 3, got {len(new_jobs)}"
        assert deduplicator.file_sha is None

        print("  └ [OK] 404 파일 미존재 시 전체 신규 공고 수집 통과")
        print("✅ [TEST SUCCESS] 신규 파일 전체 수집 테스트 통과!\n")
    except AssertionError as e:
        print(f"❌ [TEST FAIL] 신규 파일 테스트 실패: {e}\n")
        raise e


@patch("requests.put")
@patch("requests.get")
def test_save_processed_jobs(mock_get, mock_put, sample_jobs):
    print("\n[TEST START] Deduplicator - 처리 완료 ID GitHub 저장 테스트")
    try:
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {
            "content": base64.b64encode(b"[]").decode("utf-8"),
            "sha": "old_sha"
        }
        mock_get.return_value = mock_get_res

        mock_put_res = MagicMock()
        mock_put_res.status_code = 200
        mock_put.return_value = mock_put_res

        deduplicator = JobDeduplicator(repo_slug="user/repo", github_token="mock_token")
        deduplicator.save_processed_jobs(sample_jobs[:2])

        assert mock_put.called, "PUT 요청이 실행되지 않았습니다."
        call_args = mock_put.call_args[1]
        payload = call_args["json"]

        assert payload["sha"] == "old_sha"
        assert "chore: update processed job IDs" in payload["message"]

        saved_ids = set(json.loads(base64.b64decode(payload["content"]).decode("utf-8")))
        assert saved_ids == {"wanted_1001", "wanted_1002"}

        print("  └ [OK] GitHub API 페이로드 검증 완료")
        print("✅ [TEST SUCCESS] GitHub 처리 ID 저장 테스트 통과!\n")
    except AssertionError as e:
        print(f"❌ [TEST FAIL] GitHub 저장 테스트 실패: {e}\n")
        raise e


def test_is_expired_deadline():
    print("\n[TEST START] Deduplicator - 마감일 미경과 및 마감 공고 판별 테스트")
    deduplicator = JobDeduplicator()

    # Past date (마감됨)
    assert deduplicator.is_expired_deadline("2020-01-01") is True
    assert deduplicator.is_expired_deadline("2020.01.01") is True

    # Future / Active date (마감 안됨)
    assert deduplicator.is_expired_deadline("2099-12-31") is False
    assert deduplicator.is_expired_deadline("상시 채용") is False
    assert deduplicator.is_expired_deadline("채용시 마감") is False
    assert deduplicator.is_expired_deadline("") is False

    print("✅ [TEST SUCCESS] 마감일 판별 테스트 통과!\n")