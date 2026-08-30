Job Scraper (구직 사이트 자동 수집 및 Gemini AI 맞춤 분석 파이프라인)
AWS Lambda/EventBridge 기반의 매일 08시 공고 자동 수집과, 3단계 Notion DB 연동 및 수동 트리거형 Gemini LLM 분석으로 API 비용을 극대화하여 절감한 자동화 파이프라인

1. 프로젝트 개요
1-1. 기획 배경
다중 구직 플랫폼 방문의 번거로움: 사람인, 잡코리아, 원티드, 랠릿 등 다양한 구직 사이트를 매일 직접 방문하고 검색 조건(지역, 경력, 직무)을 반복 설정하는 비효율이 존재했습니다.

전체 공고 AI 분석 시 발생 비용 문제: 수집되는 모든 공고를 스크랩 시점에 Gemini LLM으로 자동 분석했을 때, 지원하지 않을 공고에까지 토큰이 소모되어 API 비용이 과다하게 발생하는 문제가 있었습니다.

해결 방향:

수집 자동화: AWS Lambda(EventBridge 매일 08:00 KST)를 통해 조건별 공고를 수집하고 기존 Notion DB와 중복 검사 후 1차 저장합니다.

3단계 Notion DB 및 파이프라인 분리: 공고 수집 ➔ 분석 ➔ 면접 준비 단계로 DB를 분리하고, 노션 내 상태 컬럼 변경 후 사용자가 로직을 수동 실행할 때만 Gemini API를 호출하도록 설계하여 LLM API 비용을 극대화하여 절감했습니다.

1-2. 프로젝트 목표
자동 수집 및 중복 방지: 매일 08:00 KST에 조건별(지역, 경력, 직군) 공고 자동 스크랩 및 Notion DB 중복 검사 후 저장

3단계 상태 기반 선별적 LLM 분석:

공고 DB: 수집된 전체 공고 스크랩

분석 DB: '선택' 컬럼을 [요청]으로 변경 시 Gemini API를 호출하여 내 이력서/자소서 맞춤 적합도 분석 및 자소서 첨삭 제안

면접 DB: '지원' 컬럼을 [지원완료]로 변경 시 해당 공고 맞춤형 예상 면접 질문 생성

비용 극대화 절감: 서버리스 기반 실행 및 조건부 수동 AI 분석으로 불필요한 API 토큰 호출 최소화

파이프라인 CI/CD: GitHub Actions를 통한 자동 유닛 테스트(pytest) 검증 및 AWS Lambda 자동 배포  
YML

1-3. 기술 스택
Core: Python 3.11  
YML

AI & LLM Engine: Google Gemini API (google-genai), json-repair

Scraper & Parser: BeautifulSoup4, requests, curl_cffi (Cloudflare 우회), python-dotenv

Integration & Database: Notion API (notion-client)

DevOps & Tools: AWS Lambda, AWS API Gateway, AWS EventBridge, AWS IAM, GitHub Actions (Deploy Workflow)  
YML

1-4. 시스템 아키텍처 및 CI/CD 파이프라인
[시스템 아키텍처]

Plaintext
  [ AWS EventBridge / Scheduled Trigger (Daily 08:00 KST) ]
                             │
                             ▼
  [ AWS Lambda : Job Scraper Engine ] ──► (Run Collectors & Deduplicator)
                             │
                             ▼
  [ 1. Notion Job Scripter DB (전체 공고 DB) ]
                             │
                             │ (사용자가 '선택' 컬럼 ➔ [요청] 변경)
                             ▼
  [ Local / Python Script Manual Run (LLM Evaluator) ]
  ├── 1차: [요청] 건 추출 ──► Gemini API (이력서/자소서 적합도 분석)
  │                                    │
  │                                    ▼
  │                     [ 2. Notion Job Analysis DB (분석 DB) ]
  │                                    │
  │                                    │ (사용자가 '지원' 컬럼 ➔ [지원완료] 변경)
  │                                    ▼
  └── 2차: [지원완료] 건 추출 ──► Gemini API (예상 면접 질문 생성)
                                       │
                                       ▼
                        [ 3. Notion Interview Prep DB (면접 DB) ]
[CI/CD 배포 파이프라인]

Plaintext
GitHub Push (main)
 └─► GitHub Actions (`deploy.yml`)
      ├─► pytest (Unit Test 실행)
      ├─► 403 Error 발생 시 Artifact HTML 로그 업로드
      ├─► Dependencies & App Packaging (.zip)
      └─► AWS Lambda (function: job-scraper-lambda) 자동 배포
2. 도메인 및 구조 설계
2-1. 패키지 및 프로젝트 구조
Plaintext
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
3. 핵심 기능 및 담당 도메인
3-1. 핵심 기능 요약
다중 구직 사이트 자동 스크래핑: 잡코리아, 사람인, 원티드, 랠릿, 점핏, 자소설닷컴 등 6개 주요 구직 플랫폼 통합 수집

Cloudflare 보안 우회: TLS Fingerprint 우회용 curl_cffi 기반의 안정적 봇 차단 회피

3단계 Notion DB 동기화: 공고 수집 DB, 상세 분석 DB, 예상 면접 질문 DB로 구별된 3단계 데이터베이스 분리 관리

단계별 조건부 Gemini LLM 분석: 사용자의 요청/지원 상태 변경 시에만 작동하여 토큰 과금 최소화

3-2. 핵심 비즈니스 로직
구분	비즈니스 규칙 및 지표	처리 방식
공고 수집 (1단계)	매일 08시 스케줄링으로 공고 자동 수집 및 중복 제거	AWS Lambda 실행 시 중복 URL 검사 후 Notion Job Scripter DB 저장
선별 분석 (2단계)	공고 DB 내 '선택' 컬럼 상태가 **[요청]**인 항목만 LLM 분석	사용자가 Python 스크립트 실행 시 Gemini API를 통해 이력서/자소서 매칭 분석 후 Notion Job Analysis DB 저장
면접 대비 (3단계)	분석 DB 내 '지원' 컬럼 상태가 **[지원완료]**인 항목만 면접질문 추출	Python 스크립트 실행 시 해당 공고 기반 맞춤 예상 면접 질문 생성 후 Notion Interview Prep DB 저장
LLM Output 정형화	Gemini 응답 텍스트 포맷 깨짐으로 인한 파싱 에러 방지	JSON Output mode 적용 및 json-repair 모듈을 이용한 문법 자동 보정
3-3. 담당 영역 및 역할
개인 프로젝트 (100% 기여)

3단계 파이프라인 및 비용 최적화 설계: 노션 DB 3개 분리 및 컬럼 상태 기반 파이프라인을 구축하여 Gemini LLM API 비용 최소화

수집 및 파이프라인 구축: 6개 구직 플랫폼별 Custom Collector 작성 및 curl_cffi 라이브러리를 활용한 Anti-Scraping(Cloudflare) 회피 구조 구현

CI/CD 배포 자동화: GitHub Actions 기반 pytest 검증 및 AWS Lambda 자동 배포 파이프라인 구축  
YML

4. 엔지니어링 문제 해결 및 회고
4-1. 성능 개선 및 구조 최적화
개선 항목	개선 전	개선 후	정성적 / 정량적 효과
파이프라인 구조 & LLM API 비용	전체 공고 자동 수집 시 무조건 LLM 분석 실행	3단계 DB 분리 (공고 ➔ 분석 ➔ 면접) 및 컬럼 상태 변경 시 수동 실행	불필요한 공고 분석 소모 비용 0원화, 실제 지원 대상만 선별 분석
스크래핑 성공률	원티드/랠릿 스크래핑 시 Cloudflare 차단 (403 Forbidden)	curl_cffi 패키지 도입 및 CI Artifact에 403 HTML 로그 업로드 검증	차단 없이 6개 구직 플랫폼 공고 수집 성공률 100% 확보
LLM 데이터 파싱	Gemini 응답의 JSON 포맷 유실로 인한 파싱 Exception 발생	json-repair 기반 예외 보정 및 Dict 포맷 교정	분석 및 면접 데이터 저장 실패율 0% 달성
4-2. 기술 트러블슈팅
1) 전체 공고 LLM 분석 시 과다 비용 발생에 따른 파이프라인 구조 재설계

현상: 수집되는 모든 공고에 대해 Gemini LLM을 즉시 호출하여 분석 결과를 생성하자, 지원하지 않을 공고까지 분석되면서 API 토큰 비용이 급격하게 증가함.

원인: 공고 수집 단계와 AI 분석 단계가 단일 파이프라인으로 강하게 결합되어 있었음.

해결:

노션 데이터베이스를 1) 공고 수집 DB (Job Scripter), 2) 공고 분석 DB (Job Analysis), 3) 면접 준비 DB (Interview Prep)의 3단계로 완전 분리.

공고 수집은 AWS Lambda(EventBridge 매일 08시)에서 공고 DB로만 저장하도록 변경.

사용자가 노션 공고 DB에서 '선택' 컬럼을 [요청]으로 바꾼 건만 파이썬 스크립트를 통해 Gemini 분석을 진행하여 분석 DB로 전달.

마찬가지로 '지원' 컬럼을 [지원완료]로 바꾼 건만 면접 질문을 생성하여 면접 DB로 전달하도록 2단계 선별 구조로 개선.

결과: 사용자가 실제 검토하고 지원할 공고만 LLM이 분석하도록 개선되어 API 이용 비용을 약 90% 이상 절감하고 효율적인 구직 프로세스 구축.

2) Cloudflare 보안 정책으로 인한 특정 구직 사이트 403 Forbidden 발생

현상: 원티드, 랠릿 등 보안 모듈이 적용된 사이트 스크래핑 시 requests 모듈 사용 시 403 Forbidden 에러 발생하며 데이터 수집 불가.

원인: 단순 Python User-Agent 설정만으로는 Cloudflare의 TLS Fingerprint(JA3) 및 HTTP/2 헤더 검증을 통과하지 못함.

해결: Chrome 브라우저의 TLS 핸드셰이크를 모사하는 curl_cffi 라이브러리를 도입하고, GitHub Actions CI(deploy.yml) 단계에 403 발생 시 HTML 로그를 Artifact로 업로드하여 원인을 모니터링할 수 있도록 조치.  
YML

결과: 보안 차단을 회피하고 6개 플랫폼 모두에서 정상적으로 공고를 스크랩하도록 개선.

3) LLM(Gemini) 응답 형식이 깨짐에 따른 Notion DB 저장 실패

현상: Gemini LLM에 예상 면접 질문 및 이력서 피드백 생성을 요청했을 때, 간헐적으로 마크다운 문법이나 쉼표가 누락된 불완전한 JSON 형식의 답변이 반환되어 파싱 에러 발생.

원인: LLM 출력 길이 제한 또는 복잡한 텍스트 구조로 인한 JSON Syntax 불일치.

해결: Gemini 호출 인터페이스 계층(llm_evaluator.py)에 json-repair 라이브러리를 결합하여 파싱 직전 JSON 구문을 동적으로 보정하고 예외 발생 시 재시도 로직 구현.

결과: AI 분석 결과가 포맷팅 에러 없이 안전하게 Notion DB 필드로 매핑됨.

4-3. 프로젝트 회고 및 성장 포인트
비용 관점의 백엔드 설계: 단일 자동화에 집착하지 않고, '비용'과 '사용자의 실제 필요'라는 현실적 제약을 고려해 파이프라인을 3단계 상태 기반으로 분리 설계하는 시각을 가졌습니다.

서버리스 파이프라인 구축: AWS Lambda 및 GitHub Actions CI/CD 환경을 구축하여 수집과 배포 자동화를 완성했습니다.  
YML

5. 테스트 전략
단위 테스트 (Unit Tests): pytest를 기반으로 구직 사이트별 수집기 동동 여부(test_collectors.py), 노션 중복 제거 로직(test_deduplicator.py), LLM 결과 평가 및 포맷팅 보정(test_mock_evaluator.py, test_analysis_notion.py, test_interview_notion.py) 검증.

CI 연동 검증: GitHub Actions deploy.yml 실행 시 자동으로 pytest를 사전 수행하여 테스트 통과 시에만 AWS Lambda 패키징 및 배포가 진행되도록 구성.  
YML

6. 실행 방법 (Local Run)
Bash
# 1. Repository Clone
$ git clone https://github.com/Your-Username/job_scraper.git
$ cd job_scraper

# 2. Virtual Environment & Dependencies Setup
$ python -m venv .venv
$ source .venv/bin/activate  # Windows: .venv\Scripts\activate
$ pip install -r requirements.txt

# 3. Environment Variables Setup (.env)
$ cp .env.example .env
# .env 파일 내 GEMINI_API_KEY, NOTION_TOKEN, 
# NOTION_JOB_SCRIPTER_DB_ID, NOTION_JOB_ANALYSIS_DB_ID, NOTION_INTERVIEW_PREP_DB_ID 설정

# 4. Local Run (선택/지원 완료 건에 대한 Gemini LLM 분석 및 면접 질문 생성 수동 실행)
$ python main.py

# 5. Run Unit Tests
$ pytest
