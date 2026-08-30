# Job Scraper

### 구직 사이트 자동 수집 및 Gemini AI 맞춤 분석 파이프라인

AWS Lambda/EventBridge 기반의 **매일 08시 공고 자동 수집**과 **3단계 Notion DB 연동**, **수동 트리거형 Gemini LLM 분석**을 결합하여 불필요한 LLM API 호출을 최소화한 자동화 파이프라인입니다.

---

## 1. 프로젝트 개요

### 1-1. 기획 배경

#### 다중 구직 플랫폼 방문의 번거로움

사람인, 잡코리아, 원티드, 랠릿 등 다양한 구직 사이트를 매일 직접 방문하고 검색 조건(지역, 경력, 직무)을 반복 설정해야 하는 비효율이 존재했습니다.

#### 전체 공고 AI 분석 시 발생하는 비용 문제

수집되는 모든 공고를 스크랩 시점에 Gemini LLM으로 자동 분석할 경우, 실제 지원하지 않을 공고에도 토큰이 소모되어 API 비용이 과다하게 발생하는 문제가 있었습니다.

#### 해결 방향

1. **수집 자동화**

   * AWS Lambda + EventBridge를 활용하여 매일 08:00 KST에 조건별 공고 자동 수집
   * 기존 Notion DB와 URL 기준 중복 검사 후 1차 저장

2. **3단계 Notion DB 및 파이프라인 분리**

   * 공고 수집 → 분석 → 면접 준비 단계로 DB 분리
   * 사용자가 Notion 내 상태 컬럼을 변경한 경우에만 Gemini API를 호출
   * 불필요한 LLM 호출을 최소화하여 API 비용 절감

---

### 1-2. 프로젝트 목표

* **자동 수집 및 중복 방지**

  * 매일 08:00 KST에 조건별(지역, 경력, 직군) 공고 자동 스크랩
  * Notion DB 중복 검사 후 신규 공고 저장

* **3단계 상태 기반 선별적 LLM 분석**

  * 공고 DB: 수집된 전체 공고 저장
  * 분석 DB: 선택 컬럼이 [요청]으로 변경된 공고만 Gemini API를 호출하여 이력서/자소서 맞춤 적합도 분석 및 첨삭 제안
  * 면접 DB: 지원 컬럼이 [지원완료]로 변경된 공고만 맞춤형 예상 면접 질문 생성

* **LLM API 비용 절감**

  * 서버리스 기반 자동 수집
  * 상태 기반 수동 AI 분석을 통해 불필요한 토큰 호출 최소화

* **CI/CD 자동화**

  * GitHub Actions를 통한 pytest 자동 검증
  * 테스트 통과 후 AWS Lambda 자동 배포

---

### 1-3. 기술 스택

| 분류                         | 기술                                                       |
| -------------------------- | ------------------------------------------------------------ |
| **Core**                   | Python 3.11                                                  |
| **AI & LLM**               | Google Gemini API (google-genai), json-repair                |
| **Scraper & Parser**       | BeautifulSoup4, requests, curl_cffi, python-dotenv           |
| **Integration & Database** | Notion API (notion-client)                                   |
| **DevOps & Tools**         | AWS Lambda, AWS API Gateway, AWS EventBridge, GitHub Actions |
| **Test**                   | pytest                                                       |

---

### 1-4. 시스템 아키텍처 및 CI/CD 파이프라인

#### 시스템 아키텍처

```text
  [ AWS EventBridge / Scheduled Trigger (Daily 08:00 KST) ]
                             │
                             ▼
  [ AWS Lambda : Job Scraper Engine ] ──► (Run Collectors & Deduplicator)
                             │
                             ▼
  [ 1. Notion Job Scripter DB (전체 공고 DB) ]
                             │
                             │ 사용자가 '선택' 컬럼 → [요청] 변경
                             ▼
  [ Local / Python Script Manual Run (LLM Evaluator) ]
  ├── 1차: [요청] 건 추출
  │          └──► Gemini API
  │                └── 이력서/자소서 적합도 분석
  │
  │                                    ▼
  │                     [ 2. Notion Job Analysis DB (분석 DB) ]
  │                                    │
  │                                    │ 사용자가 '지원' 컬럼 → [지원완료] 변경
  │                                    ▼
  └── 2차: [지원완료] 건 추출
             └──► Gemini API
                   └── 예상 면접 질문 생성
                                        │
                                        ▼
                        [ 3. Notion Interview Prep DB (면접 DB) ]
```

#### CI/CD 배포 파이프라인

```text
GitHub Push (main)
 └─► GitHub Actions (deploy.yml)
      ├─► pytest (Unit Test 실행)
      ├─► 403 Error 발생 시 Artifact HTML 로그 업로드
      ├─► Dependencies & App Packaging (.zip)
      └─► AWS Lambda (job-scraper-lambda) 자동 배포
```

---

# 2. 도메인 및 구조 설계

## 2-1. 패키지 및 프로젝트 구조

```text
job_scraper/
├── .github/workflows/          # CI/CD 배포 파이프라인
│   ├── daily_job.yml           # 수동 테스트 실행 워크플로우 (workflow_dispatch)
│   └── deploy.yml              # main 푸시 시 pytest 수행 및 AWS Lambda 자동 배포
├── app/
│   ├── application/            # 수집 및 분석 비즈니스 오케스트레이션
│   ├── domain/                 # 공고/분석 데이터 모델 및 인터페이스 정의
│   ├── infrastructure/         # 사이트별 스크래퍼, Gemini LLM, 파서 구현체
│   └── presentation/           # 3개 Notion DB(수집/분석/면접) 연동 및 알림 계층
│       ├── notion_scripter_notifier.py # 1. 공고 수집 DB 저장
│       ├── notion_analysis_notifier.py # 2. 분석 DB 저장
│       └── notion_interview_notifier.py# 3. 면접 DB 저장
├── tests/                      # 수집기, 중복 검사, LLM 평가 단위 테스트
├── assets/                     # 이력서/포트폴리오 문서 자원
├── lambda_function.py          # AWS Lambda 실행 엔트리포인트 (매일 08시 공고 수집용)
├── main.py                     # 로컬 실행 엔트리포인트 (선별적 LLM 분석/면접 스크립트 실행)
└── requirements.txt            # 파이썬 의존성 패키지 목록
```

---

# 3. 핵심 기능 및 담당 도메인

## 3-1. 핵심 기능 요약

* **다중 구직 사이트 자동 스크래핑**

  * 잡코리아, 사람인, 원티드, 랠릿, 점핏, 자소설닷컴 등 6개 주요 구직 플랫폼 통합 수집

* **Cloudflare 보안 우회**

  * curl_cffi를 활용하여 브라우저와 유사한 TLS Fingerprint 기반 요청 구현
  * Cloudflare 차단으로 인한 403 Forbidden 대응

* **3단계 Notion DB 동기화**

  * 공고 수집 DB, 상세 분석 DB, 예상 면접 질문 DB로 구별된 3단계 데이터베이스 분리 관리

* **단계별 조건부 Gemini LLM 분석**

  * 사용자가 상태를 변경한 공고만 Gemini API를 호출
  * 불필요한 토큰 사용 최소화

---

## 3-2. 핵심 비즈니스 로직

| 구분                      | 비즈니스 규칙                                    | 처리 방식                                                                            |
| -----------------------| ------------------------------------------ | -------------------------------------------------------------------------------- |
| **공고 수집 (1단계)**    | 매일 08시 스케줄링으로 공고 자동 수집 및 중복 제거             | AWS Lambda 실행 시 URL 중복 검사 후 Notion Job Scripter DB 저장                           |
| **선별 분석 (2단계)**    | 공고 DB 내 선택 컬럼 상태가 [요청]인 항목만 LLM 분석     | 사용자가 Python 스크립트 실행 시 Gemini API를 통해 이력서/자소서 매칭 분석 후 Notion Job Analysis DB 저장 |
| **면접 대비 (3단계)**    | 분석 DB 내 지원 컬럼 상태가 [지원완료]인 항목만 면접 질문 생성 | Python 스크립트 실행 시 해당 공고 기반 맞춤 예상 면접 질문 생성 후 Notion Interview Prep DB 저장         |
| **LLM Output 정형화** | Gemini 응답 텍스트 포맷 오류 방지                     | JSON Output Mode 적용 및 json-repair를 이용한 JSON 문법 자동 보정                           |

---

## 3-3. 담당 영역 및 역할

### 개인 프로젝트 (100% 기여)

* **3단계 파이프라인 및 비용 최적화 설계**

  * Notion DB 3개 분리
  * 컬럼 상태 기반으로 단계별 파이프라인 구성
  * 불필요한 Gemini LLM API 호출 최소화

* **수집 및 파이프라인 구축**

  * 6개 구직 플랫폼별 Custom Collector 구현
  * curl_cffi를 활용한 Anti-Scraping 대응 구조 구현

* **CI/CD 배포 자동화**

  * GitHub Actions 기반 pytest 검증
  * AWS Lambda 자동 배포 파이프라인 구축

---

# 4. 엔지니어링 문제 해결 및 회고

## 4-1. 성능 개선 및 구조 최적화

| 개선 항목                     | 개선 전                                             | 개선 후                                           | 정성적 / 정량적 효과                       |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------- | ---------------------------------- |
| **파이프라인 구조 & LLM API 비용** | 전체 공고 자동 수집 시 무조건 LLM 분석 실행                      | **3단계 DB 분리(공고 → 분석 → 면접)** 및 컬럼 상태 변경 시 수동 실행 | 불필요한 공고 분석 비용 최소화, 실제 지원 대상만 선별 분석 |
| **스크래핑 성공률**              | 원티드/랠릿 스크래핑 시 Cloudflare 차단으로 403 Forbidden 발생 | curl_cffi 도입 및 CI Artifact에 403 HTML 로그 업로드  | 6개 구직 플랫폼 정상 수집                    |
| **LLM 데이터 파싱**            | Gemini 응답 JSON 포맷 유실로 파싱 Exception 발생            | json-repair 기반 예외 보정 및 Dict 포맷 교정            | 분석 및 면접 데이터 저장 안정성 향상              |

---

## 4-2. 기술 트러블슈팅

### 1) 전체 공고 LLM 분석 시 과다 비용 발생에 따른 파이프라인 구조 재설계

**현상**

수집되는 모든 공고에 대해 Gemini LLM을 즉시 호출하여 분석 결과를 생성하자, 실제 지원하지 않을 공고까지 분석되면서 API 토큰 비용이 급격하게 증가했습니다.

**원인**

공고 수집 단계와 AI 분석 단계가 단일 파이프라인으로 강하게 결합되어 있었습니다.

**해결**

* Notion 데이터베이스를 다음 3단계로 완전 분리

  1. Job Scripter — 공고 수집 DB
  2. Job Analysis — 공고 분석 DB
  3. Interview Prep — 면접 준비 DB

* 공고 수집은 AWS Lambda + EventBridge를 통해 매일 08시에 실행

* 수집된 공고는 Job Scripter DB에만 저장

* 사용자가 선택 컬럼을 [요청]으로 변경한 공고만 Python 스크립트를 통해 Gemini 분석 수행

* 분석 결과는 Job Analysis DB로 전달

* 사용자가 지원 컬럼을 [지원완료]로 변경한 공고만 면접 질문 생성

* 생성된 결과는 Interview Prep DB로 전달

**결과**

사용자가 실제 검토하고 지원할 공고만 LLM이 분석하도록 구조를 개선하여 **API 이용 비용을 약 90% 이상 절감**하고 효율적인 구직 프로세스를 구축했습니다.

---

### 2) Cloudflare 보안 정책으로 인한 특정 구직 사이트 `403 Forbidden` 발생

**현상**

원티드, 랠릿 등 보안 모듈이 적용된 사이트를 requests 모듈로 스크래핑할 경우 403 Forbidden이 발생하며 데이터 수집이 불가능했습니다.

**원인**

단순 Python User-Agent 설정만으로는 Cloudflare의 TLS Fingerprint(JA3) 및 HTTP/2 헤더 검증을 통과하지 못했습니다.

**해결**

* Chrome 브라우저의 TLS 핸드셰이크를 모사하는 curl_cffi 도입
* GitHub Actions CI(deploy.yml) 단계에서 403 발생 시 HTML 로그를 Artifact로 업로드
* CI 환경에서도 스크래핑 상태를 확인할 수 있도록 모니터링 구조 구성

**결과**

Cloudflare 차단 문제를 해결하고 6개 구직 플랫폼에서 정상적으로 공고를 수집할 수 있도록 개선했습니다.

---

### 3) LLM(Gemini) 응답 형식이 깨짐에 따른 Notion DB 저장 실패

**현상**

Gemini LLM에 예상 면접 질문 및 이력서 피드백 생성을 요청했을 때, 간헐적으로 마크다운 문법이나 쉼표가 누락된 불완전한 JSON이 반환되어 파싱 에러가 발생했습니다.

**원인**

LLM 출력 길이 제한 또는 복잡한 텍스트 구조로 인해 JSON Syntax가 깨지는 문제가 발생했습니다.

**해결**

* Gemini 호출 인터페이스 계층(llm_evaluator.py)에 json-repair 라이브러리 결합
* 파싱 직전 JSON 구문 자동 보정
* 예외 발생 시 재시도 로직 적용
* 최종적으로 Notion DB에 저장 가능한 Dict 형태로 변환

**결과**

AI 분석 결과의 JSON 포맷 오류를 보정하여 Notion DB 필드에 안정적으로 저장할 수 있도록 개선했습니다.

---

## 4-3. 프로젝트 회고 및 성장 포인트

* **비용 관점의 백엔드 설계**

  * 단순히 자동화 범위를 늘리는 데 집중하지 않고, 비용과 실제 사용자의 필요를 함께 고려하여 파이프라인을 설계했습니다.
  * 공고 수집 → 분석 → 면접 준비 단계를 분리하여 **필요한 데이터에만 LLM을 적용하는 구조**를 구현했습니다.

* **서버리스 파이프라인 구축**

  * AWS Lambda 및 EventBridge를 기반으로 공고 수집 자동화를 구성했습니다.
  * GitHub Actions CI/CD를 통해 테스트와 배포까지 자동화했습니다.

---

# 5. 테스트 전략

* **단위 테스트(Unit Tests)**

  * pytest 기반으로 주요 도메인 및 기능 테스트
  * test_collectors.py: 구직 사이트별 Collector 정상 동작 검증
  * test_deduplicator.py: Notion 기반 공고 중복 제거 로직 검증
  * test_mock_evaluator.py: LLM 결과 평가 및 포맷 보정 검증
  * test_analysis_notion.py: 분석 결과 Notion 저장 로직 검증
  * test_interview_notion.py: 면접 데이터 Notion 저장 로직 검증

* **CI 연동 검증**

  * GitHub Actions `deploy.yml` 실행 시 `pytest` 자동 수행
  * 테스트 통과 시에만 AWS Lambda 패키징 및 배포 진행

---

# 6. 실행 방법 (Local Run)

```bash
# 1. Repository Clone
git clone https://github.com/Your-Username/job_scraper.git
cd job_scraper

# 2. Virtual Environment & Dependencies Setup
python -m venv .venv
source .venv/bin/activate # Windows .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment Variables Setup
cp .env.example .env # .env 파일에 아래 환경변수 설정
# GEMINI_API_KEY, NOTION_TOKEN, NOTION_JOB_SCRIPTER_DB_ID, NOTION_JOB_ANALYSIS_DB_ID, NOTION_INTERVIEW_PREP_DB_ID=

# 4. Local Run(선택된 공고 및 지원 완료 공고에 대한 Gemini LLM 분석 및 면접 질문 생성 수동 실행
python main.py

# 5. Run Unit Tests
pytest
```
