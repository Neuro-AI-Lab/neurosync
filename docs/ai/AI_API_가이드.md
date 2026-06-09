# AI 챔피언 대회 — 국산 LLM/AI API 통합 가이드

> **Version**: 1.1
> **Created**: 2026-06-02 (v1.0) / **Updated**: 2026-06-04 (v1.1)
> **Source**: 프로젝트 루트 `references/*.pdf` (KT, LG AI연구원, NC AI, SKT, 업스테이지) 5종 OCR 분석
> **Owner**: AI Research 팀
> **목적**: Neuro-Sync 멀티 LLM 오케스트레이션 설계의 기술 선택 근거 문서
>
> **OCR 신뢰도 면책**: 본 문서의 수치·고유명사는 PDF 원본의 한국어 OCR 결과를 기반으로 정리됨. ±1% 오차 또는 일부 표 셀의 누락 가능성이 있으니, **벤더 공식 콘솔/문서로 최종 검증 권장**.

---

## 0. Executive Summary

| 벤더 | 모델 | 파라미터 | 라이선스 | 접근 방식 | Neuro-Sync 활용 |
|------|------|---------|---------|----------|----------------|
| **KT** | Mi:dm K 2.0 Base | 11.5B (Dense) | **MIT** | HuggingFace 자체 호스팅 | 자가호스팅 PHI 처리, On-prem 추론 |
| **LG AI** | K-EXAONE | 236B-A23B (MoE) | TBD | FriendliAI API | 메인 리즈닝 엔진(다국어/Reasoning) |
| **SKT** | A.X K1 | 519B-A33B (MoE) | TBD | OpenAI-compatible API | Agentic 오케스트레이터(Tool/Plan) |
| **NC AI** | VARCO (멀티모달) | N/A | SaaS only | api.varco.ai | 보조 — 환자 교육용 시각 자산 생성 |
| **Upstage** | Solar Pro 3 + Document Parse + Information Extract | 102.6B-12.8B (MoE) | SaaS | console.upstage.ai | 사전 문진 PDF OCR, 구조화 추출 |

**4-LLM 오케스트레이션 매핑 (Neuro-Sync PRD §5.3 Architecture 기준):**
- 1차 임상 요약 → **K-EXAONE** (다국어 + Hybrid Reasoning)
- Agentic 라우팅 + Tool call → **A.X K1** (Agentic 벤치마크 1위)
- 자가호스팅 보조 추론 (PHI 분리) → **Mi:dm K 2.0 Base** (MIT, On-prem 가능)
- 사전 문진 PDF/스캔본 처리 → **Upstage Document Parse + Information Extract**
- 환자 교육 보조 자산 생성(선택) → **VARCO** (3D/Sound/Voice)

---

## 1. KT — Mi:dm K 2.0 Base

### 1.1 모델 라인업
| 항목 | 값 |
|------|---|
| 모델명 | Mi:dm 2.0 Base (Instruct) |
| 파라미터 | 11.5B (Dense) |
| 학습 방식 | **From Scratch**, Bilingual(한/영) |
| 컨텍스트 | 32K → **128K** (CPT로 확장) |
| 라이선스 | **MIT** (연구·상업 활용 제약 없음) |
| 출시 | 2025-07-04 첫 공개 / 2025-08-08 기술 블로그 / **2025-10-29 vLLM Function Calling 지원 추가** |
| 다음 업데이트 | 2026년 Base Update (AX 도메인 강화) |

### 1.2 핵심 특징
- **한국어 특화 + RAG 강력**: KMMLU, HAERAE 벤치마크에서 글로벌 오픈소스 동급 대비 우수
- **호랑이 리더보드 1위** (2025-07-09)
- **STEM & Reasoning** 강화, **Function Call** 지원 (vLLM parser 통합)
- **멀티턴 SFT**: 약 15만 개 멀티턴 데이터셋 (평균 20턴)
- **Long Context 128K**: 자체 합성 한국어 데이터 + 20B 규모 CPT
- **RAI(Responsible AI)** 원칙 적용 (안전성 사전 차단)

### 1.3 접근 방법
- **HuggingFace Repo**: `K-intelligence/Midm-2.0-Base-Instruct`
- **GitHub Repo**: <https://github.com/K-intelligence-Midm/Midm-2.0>
- **튜토리얼 5종 제공** (OCR에서 4종 확인, 5번째는 원본 페이지 추가 확인 필요):
  1. Fine-tuning (`trl` + `SFTTrainer` + SimpleQA-GenX2 데이터셋)
  2. Inference (최적 생성 세팅)
  3. Open WebUI 연동 (MCP, RAG)
  4. Prompting 예시 모음
  5. (GitHub Tutorials 페이지에서 직접 확인 필요)
- **가격**: **무료** (MIT 라이선스 — 모델 가중치 자체에 사용료 없음, 자가호스팅 GPU 비용만 발생)
- **컨택**: `midm-llm@kt.com`

### 1.4 KT AX 활용 사례
- **KT AICC**: AI 컨택센터 자동화/상담 품질
- **Agent Connector**: 지능형 AI 네트워크 운용/장애 예측
- **Agentic Fabric**: 다중 AI 에이전트 통합 오케스트레이션 플랫폼

### 1.5 Neuro-Sync 활용 적합도
- **강점**: MIT 라이선스 + 11.5B 소형 → **On-prem/사내 GPU 자가호스팅** 가능 → **PHI 분리 추론**에 최적. 한국어 의료 도메인 RAG 강력.
- **약점**: 파라미터 작음 → 복잡한 리즈닝은 K-EXAONE/A.X K1 대비 한계.
- **활용 제안**: PHQ-9/GAD-7 답변 1차 분류, 키워드 추출, 의료 동의서 RAG 등 **PHI를 외부 API에 보내지 않아야 하는 작업** 전담.

---

## 2. LG AI연구원 — K-EXAONE

### 2.1 모델 라인업
| 항목 | 값 |
|------|---|
| 모델명 | K-EXAONE (2차수 모델, 2026-06 공개 예정) |
| 아키텍처 | **MoE 236B-A23B** (활성 파라미터 23B) |
| 비교 모델 | Qwen3-235B 동등 이상 |
| 학습 인프라 | NVIDIA B200 × 512 |
| 다국어 | **6개국어** (한국어, 영어, 스페인어, 독일어, 일본어, 베트남어) |
| 라이선스 | TBD (정부 「독자 AI 파운데이션 모델」 프로젝트 결과물) |

### 2.2 핵심 특징
1. **효율성**:
   - 전체 236B 중 23B만 활성화 (MoE)
   - **Hybrid Attention** 구조 → 메모리·연산 30% 수준 절감
   - 토크나이저 개선 → 토큰 생성 효율 30% 증가 (단어 사전 한국어 비율 50%)
   - **MTP Block**으로 답변 생성 속도 50% 개선
2. **정확도**:
   - 자체 강화학습 알고리즘 **AGAPO** 적용
   - 벤치마크: MMLU-Pro, AIME 2025, LiveCodeBench v6, τ²-Bench, IFBench, KoBALT, MMMLU, KGC-Safety
   - EXAONE-4.0-32B, gpt-oss-120b, Qwen3-235B-A22B-Thinking-2507, DeepSeek-V3.2 대비 비교
3. **추가 기능**:
   - **Hybrid Reasoning**: 일반 모드 + 추론 모드 동시 지원
   - **Tool Calling** 지원 (Slack/이메일 Webhook 예시 제공)
   - 다국어 RAG Application 가능
   - **코딩 보조** 도구로 활용 가능

### 2.3 접근 방법
- **API 제공**: **FriendliAI** 플랫폼 경유
- 추후 기술 워크샵에서 상세 설명 예정 (2026-06 출시 시점)
- **가격**: 미공개 (FriendliAI 콘솔 단가 별도 확인 필요, 대회 특전 여부 미공지)
- 1차수 결과: 미국 Epoch AI 'Notable AI Models' 등재, AAII 인덱스 세계 10위 이내 진입

### 2.4 산업 활용 사례
- 자연어 처리, Tool Calling 자동화 (메일 발송, Webhook)
- 코딩 보조 (웹페이지 생성 등)
- 다국어 RAG 챗봇

### 2.5 Neuro-Sync 활용 적합도
- **강점**: Hybrid Reasoning은 정신과 임상 추론(다중 가설 평가, 위험도 판단)에 적합. 다국어 → 외국인 환자 대응 가능.
- **약점**: 외부 API 의존(FriendliAI) → 가명정보 전송 시 **PIPA 제26조 재위탁 동의(LG ↔ FriendliAI 2단 위탁)** 필수. 정식 출시 2026-06.
- **활용 제안**: **메인 임상 요약 LLM**으로 채택. Reasoning 모드로 위험도 평가/감별진단 후보 생성. Tool Calling으로 위기 알림 워크플로 트리거.

---

## 3. SKT — A.X K1

### 3.1 모델 라인업
| 항목 | 값 |
|------|---|
| 모델명 | A.X K1 (SK텔레콤) |
| 아키텍처 | **MoE 519B-A33B** (활성 33B) → **국내 최초 500B+ 모델** |
| 학습 방식 | From Scratch |
| 라이선스 | TBD (대회 본선 시작 전 공지) |
| 후속 | **A.X K2** 2026년 6월 말 공개 예정 |

### 3.2 SKT AI 모델 히스토리
- 2019: KoBERT (최초 한국어 BERT, 누적 900만+ 다운로드)
- 2020: KoGPT-2 (최초 한국어 생성형, 누적 295만 다운로드)
- 2022–2024: A.X 1.0 → 2.0 → 3.0 (7B/18B → 7B/39B → 7B/34B)
- 2025.02: A.X 4.0 (7B/72B 비추론형 언어모델)
- 2025.07: A.X 3.1 (7B/34B 추론형), A.X 4.1, A.X Encoder (한국어 특화 이해 모델)
- **2025.12: A.X K1 (519B-A33B, 추론형)** ← §3.1 공식 스펙
- HuggingFace 누적 다운로드 약 1,135만 회

### 3.3 핵심 특징
- **DeepSeek V3.1 유사 성능** (글로벌 13개 벤치마크 기준)
- 강점 영역: **지시 이행, 에이전트, 코딩, 수학**
- **Agentic AI 벤치마크 1위** (카카오 OrchestrationBench, 최신 논문 기준):
  - Average / Call Rejection / Function Call / Plan 전 영역 정예 모델 중 1위
- **한국어 토크나이저 효율 15–17% 우월** (애국가 가사 비교)
- **장점**: 수학·과학 추론, 계획 수립·검토·작업 도출

### 3.4 접근 방법
```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("AXK1_API_KEY"),
    base_url="https://api.ax-k1.sktai.qa/v1"
)

response = client.chat.completions.create(
    model="skt/A.X-K1",
    messages=[{"role": "user", "content": "안녕"}]
)
print(response.choices[0].message.content)
```
- **OpenAI-compatible API** (개발자 편의성)
- **API Key**: TBD (본선 시작 전 발급)
- **base_url**: `https://api.ax-k1.sktai.qa/v1` (QA 환경 가능성 — 본선 시작 시점에 운영 도메인으로 변경 가능)
- **model**: `skt/A.X-K1`
- **가격**: 미공개 (대회 기간 무료 제공 여부 별도 안내 예정)
- 공식 안내: "본선 시작 전 서빙 활용 가이드 제공 예정"

### 3.5 Neuro-Sync 활용 적합도
- **강점**: Agentic 벤치마크 1위 → **멀티 에이전트 오케스트레이터** 역할 최적. Function Call/Plan 능력으로 RAG·EHR 도구 호출 안정적. OpenAI SDK 그대로 사용 가능 → 통합 빠름.
- **약점**: 외부 SaaS API → 가명정보로 변환 후 전송 (**가명처리 파이프라인** 필수, PIPA 가명정보 처리 가이드라인 준수). API Key 발급 일정 미확정.
- **활용 제안**: **Agentic Orchestrator** 역할. 환자 응답 → 위험 키워드 라우팅 → 적절한 도구(LangGraph 노드) 호출 → 임상 요약 LLM(K-EXAONE)으로 최종 합성.

---

## 4. NC AI — VARCO (멀티모달 자산)

### 4.1 제품 라인업
| 제품 | 기능 |
|------|------|
| **VARCO 3D** | 텍스트/이미지 → 3D 에셋 생성 + 편집 |
| **VARCO Sound** | 텍스트/이미지/영상 → SFX, Ambience, BGM |
| **VARCO Voice + Translation** | 다국어 더빙 영상 |
| **VARCO Art Fashion + Commerce** | 의상 디자인 + 마케팅 상세 페이지 |
| **VARCO 이미지/영상** | Text/Image Prompt → 고품질 이미지/3D 에셋/결합 영상 |

> "Via AI Realize your Creativity and Originality"

### 4.2 컨셉 — "타사 LLM의 피날레"
NC AI의 명시적 포지셔닝:
> KT, LG AI연구원, SKT, 업스테이지의 LLM 파운데이션 모델은 훌륭한 생각을 정교화 할 때 탁월합니다. 그러나 텍스트 뒤에 숨겨진 아이디어를 '눈에 보이는 에셋'으로 실체화해야 합니다. **VARCO는 다른 LLM과 혼용되어 상상을 즉시 에셋으로 변환**합니다.

**권장 파이프라인**:
1. Step 1 (타사 LLM): 스토리텔링, 핵심 로직, 세계관, 시스템 프롬프트 설계
2. Step 2 (VARCO API): 텍스트 → 고해상도 이미지/3D 텍스처/사운드/목소리

### 4.3 활용 사례
- **ANIMA 3D**: VARCO 3D + 외부 LLM → 캐릭터 대화 서비스
- **클래스링**: VARCO API + LLM → 구연동화 (교육/교보재)
- **Unity Sound Plugin**: Sound API + 바이브코딩 → 게임 사운드 즉시 생성

### 4.4 접근 방법
- **포털**: <https://api.varco.ai/ko>
- 가입 → 약관 동의 → 워크스페이스 생성 → 워크스페이스 ID 발급 → API 호출
- **대회 특전**:
  - VARCO API **무제한 사용** (대회 기간)
  - VARCO SaaS **10만 호출** 추가 제공
  - 전문 기술 교육 + 100개 팀 전용 Hotline
- **컨택**: `nakyubong@ncsoft.com` (VARCO Biz. Team)

### 4.5 Neuro-Sync 활용 적합도
- **강점**: 환자 교육 자료(이완 가이드 음성, 위기 대응 안내 영상) 생성에 즉시 활용. 의료진 교육 콘텐츠 제작.
- **약점**: 의료 도메인 직접 활용은 없음. 정신과 진단/임상에는 직접 기여하지 않음.
- **활용 제안**: **선택적 부가 기능** — Phase 2 이후 "환자 맞춤 이완 가이드 음성 생성", "위기 안내 영상" 등. **의료 핵심 파이프라인 외 보조 역할**로 분리. PHI 노출 없는 일반 안내용 자산만 생성.

---

## 5. Upstage — Solar + Document Parse + Information Extract

### 5.1 제품 라인업
| 제품 | 출시 | 용도 |
|------|------|------|
| Document OCR | 2023-04 | OCR |
| Document Parse | 2024-05 | 문서 → HTML/Markdown 변환 |
| Information Extract | 2024-08 | 비정형 → 구조화 데이터 |
| Document Classify | 2024-11 | 문서 분류 |
| Solar 10.7B / Mini / Pro / Pro 2 / Open | 2023-12 ~ 2025-06 | LLM |
| **Solar Pro 3** | **2026-01** | 최신 LLM |
| Upstage Studio | 2026-01 | 워크플로 자동화 |

### 5.2 Solar Pro 3
| 항목 | 값 |
|------|---|
| 아키텍처 | **MoE 102.6B / 활성 12.8B** |
| 학습 | **19.7조 토큰 사전학습**, NVIDIA B200 GPU, **From Scratch** |
| 컨텍스트 | **128K** 토큰 |
| 한국어 | Solar Pro 2 대비 **2배+**, 영어·일본어도 상회 |
| 라이선스 | SaaS 전용 |

**성능 비교 (Solar Pro 3 vs Pro 2)**:
- **에이전트 능력**: τ²-Bench `72.3 vs 36` (2배 상승)
- **한국어**: Ko-Arena-hard-v2 `78.2 vs 66.6`
- 자체 강화학습 RLNR 적용, 다단계 계획 유지, 오류 자가 감지, 모호 상황 판단 강화

### 5.3 Document Parse
- **입력 포맷**: PDF, 스캔 이미지 (tiff, jpeg), MS Office (xlsx, pptx) 등
- **출력**: HTML 또는 Markdown
- **파이프라인**: PDF Parser → OCR → Layout Detector → Reading Order → Heading Level → Table Recognizer → Chart Recognizer → Final Result
- **정확도/속도 (TEDS 기준)**:

| 솔루션 | TEDS | TEDS-S | NID | Avg Time(s) |
|--------|------|--------|-----|-------------|
| **Upstage Document Parse** | **96.06** | **97.25** | **96.29** | **3.77** |
| AWS Textract | 95.48 | 96.99 | 95.97 | 7.95 |
| LlamaParse | 90.73 | 76.34 | 90.53 | 10.88 |
| Unstructured | 80.26 | 89.52 | 91.78 | 6.80 |
| Google Layout Parser | 78.30 | 78.30 | 82.17 | 37.00 |
| Azure AI Document Intelligence | 77.85 | 85.74 | 87.03 | 4.44 |

- **AWS Marketplace AI Agents & Tools 부문 글로벌 2위** (구독 기준, 2026-02)
- **가격**: 본 PDF에는 단가 미기재. Upstage는 일반적으로 **페이지당 과금** 모델 사용 → `console.upstage.ai` 또는 AWS Marketplace에서 최신 단가 확인 필요

### 5.4 Information Extract
- **단일 LLM 기반 에이전틱 파이프라인**: Document Parse + LLM (Router → Sub-pipelines → Validator)
- 견적서/송장/계약서 등 → 키-값 구조 자동 추출
- **정확도 벤치마크** (KIEval, ICDAR 2025):

| 모델 | 정확도 | 시간 | 비용($/1K input tokens) |
|------|--------|------|------------------------|
| **Upstage Information Extract (250930)** | **78.32%** | **7.50s** | $0.040 |
| GPT-4.1 | 73.65% | 15.48s | $0.006 |
| Claude Sonnet 4.5 | 63.66% | 16.13s | $0.017 |
| Gemini 2.5 Flash | 76.59% | 35.68s | $0.004 |
| Gemini 2.5 Pro | 77.77% | 37.92s | $0.020 |
| Qwen 2.5 VL 72B | 68.60% | 41.83s | $0.011 |

- 비교: 전통 OCR 대비 학습 불필요 (Zero training), 누구나 약 1일 시간으로 즉시 배포

### 5.5 접근 방법
- **콘솔**: <https://console.upstage.ai>
- **교육 자료**: <https://edu.upstage.ai/course/upstage-user-guide-api>
- API 제공:
  - **Solar Chat API** (대화형 LLM)
  - **Solar Embedding API**
  - **Function Calling API**
  - **Document Parse API**
  - **Information Extract API**
  - **Upstage Studio** (노코드 워크플로)

**규모 지표**:
- 연 매출 $20M (2024)
- 일일 자동 처리 300만+ 페이지
- 국내 보험 청구 처리 70%
- 글로벌 기업 100+ / AI 엔지니어 100+ / 누적 펀딩 $150M
- CB Insights Fintech 100 (Foundation models), Insurtech 100 (Workflow / Cross-functional platforms) 선정

### 5.6 Neuro-Sync 활용 적합도
- **강점**:
  1. **Document Parse**: 정신과 PDF 사전 문진지/타원 진료 기록 OCR 핵심. TEDS 96% + 3.77s 처리는 PRD §5.3 Architecture · §5.4 Pages의 사전 문진 업로드 흐름에 즉시 적용 가능
  2. **Information Extract**: PHQ-9/GAD-7 스캔본 → 구조화 데이터 자동 매핑
  3. **Solar Pro 3**: τ²-Bench 72.3 → Tool-calling 임상 워크플로에 적합
- **약점**: SaaS only → 가명정보 전송 시 **개인정보 처리 위탁 계약 + 국내 데이터 잔류 보장 + 한국 의료법 검토** 필수
- **활용 제안**:
  - **사전 문진 PDF 업로드 파이프라인 1순위 채택** (PRD §6 Phase 1b)
  - Document Parse → Information Extract → 구조화된 환자 답변 JSON → K-EXAONE 임상 요약 입력
  - Solar Pro 3는 임시/예비 LLM으로 보유

---

## 6. Neuro-Sync 멀티 LLM 오케스트레이션 매핑 결론

### 6.1 역할 분담
```
[환자 사전 문진 PDF 업로드]
    ↓
[Upstage Document Parse + Information Extract] ── 구조화 환자 답변 JSON
    ↓
[가명처리 파이프라인 (직접식별자 마스킹 + 가명정보 변환)]
    ↓
[SKT A.X K1 — Agentic Orchestrator]
    ├── Tool: 위험 키워드 룰 엔진
    ├── Tool: 과거 진료 RAG (Mi:dm K 2.0 자가호스팅)
    └── Plan: 임상 요약 작성 단계
    ↓
[LG K-EXAONE — 임상 요약 + Reasoning Mode]
    ↓
[NC AI VARCO — 환자 교육 자산 생성(선택)]
    ↓
[Handoff Report → 임상의 대시보드]
```

### 6.2 개인 의료정보 격리 원칙 (한국 PIPA · 의료법 기준)

> PRD v1.1 §4.5 Security에서 정의한 한국 PIPA + 의료법 + 자살예방법 체계와 일치.

- **개인식별정보(직접식별자) — 외부 API 절대 전송 금지**: 실명, 주민등록번호, 연락처, 주소, 환자번호 → **KT Mi:dm K 2.0 (자가호스팅)**에서만 처리
- **가명정보(가명처리된 의료정보) — 위탁계약 체결 후 전송 가능**: 가명화된 증상 요약, 표준 척도(PHQ-9/GAD-7) 점수, 임상 코드 → SKT/LG/Upstage SaaS 사용 가능 (조건부)
- **벤더별 필요 계약 (PIPA 제26조 개인정보 처리 위탁 기준)**:
  - **SKT A.X K1**: 개인정보 처리 위탁 계약 + 가명정보 처리 가이드라인 부합 확인 + 처리 위탁 사실 정보주체 통지
  - **LG K-EXAONE (FriendliAI 경유)**: 2단 위탁 구조(LG ↔ FriendliAI) → **재위탁 동의 필수**, 위탁 사슬 전 구간 PIPA 적합성 확인
  - **Upstage**: 개인정보 처리 위탁 계약 + **국내 데이터 잔류(데이터 국외 이전 없음)** 보장 명시 + 가명정보 사용 기록 보관
- **공통 요건**: 모든 외부 LLM 호출은 **감사 로그(audit_logs, PRD §5.2)** 에 기록 + 사용 척도/요청 ID/응답 ID 보존

### 6.3 일정 의존성 (기준일: 2026-06-04)

| 의존성 | 시점 | 현재 상태 | 대체 시나리오 |
|--------|------|----------|--------------|
| **KT Mi:dm K 2.0 + vLLM Function Call** | 2025-10-29 지원 시작 | ✅ 즉시 사용 가능 | (대체 불필요) |
| **Upstage Solar Pro 3 / Document Parse / Information Extract** | 2026-01 출시 | ✅ 즉시 사용 가능 | (대체 불필요) |
| **NC AI VARCO API** | 가입 즉시 | ✅ 즉시 사용 가능 (대회 기간 무제한) | (선택 기능, 미사용 가능) |
| **LG K-EXAONE 2차수** | 2026-06 (이번 달) | 🟡 출시 임박 | 미출시 시 → EXAONE 4.0 32B 또는 Solar Pro 3로 임상 요약 대체 |
| **SKT A.X K1 API Key 발급** | 대회 본선 시작 전 | 🟡 발급 일정 미공지 | 미발급 시 → **KT Mi:dm Agentic Fabric** + Solar Pro 3 τ²-Bench 72.3 활용으로 Orchestrator 역할 분산 대체 |
| **SKT A.X K2** | 2026-06 말 (3~4주 내) | 🟡 출시 임박 | K1 대비 성능 향상 시 본선 단계에서 K1→K2 스왑 검토 |

### 6.4 선택 가이드
- **빠른 PoC**: Upstage(Document Parse) + KT Mi:dm(자가호스팅) 조합으로 시작 → 즉시 사용 가능
- **Agentic 강화**: SKT A.X K1 추가 (Key 발급 후)
- **다국어/Reasoning 확장**: LG K-EXAONE 추가 (2026-06 이후)
- **환자 교육 자산**: NC AI VARCO 옵션 (Phase 2)

---

## 7. 참고 자료 위치

| 벤더 | 원본 PDF (프로젝트 루트 `references/`) |
|------|----------------------|
| KT | `1775173432611_KT-AI_모델_및_API_활용법.pdf` (16p) |
| LG AI연구원 | `1775173440227_LG_AI연구원-AI_모델_및_API_활용법.pdf` (16p) |
| NC AI | `1775173449143_NC_AI-AI_모델_및_API_활용법.pdf` (21p) |
| SKT | `1775173454990_SKT-AI_모델_및_API_활용법.pdf` (11p) |
| 업스테이지 | `1775173460096_업스테이지-AI_모델_및_API_활용법.pdf` (26p) |

**관련 PRD/PLAN**:
- `docs/prd/PRD_neuro-sync.md` — 멀티 LLM 오케스트레이션 아키텍처 §5.1
- `docs/todo_plan/PLAN_neuro-sync.md` — Phase 0/1a/1b 실행 계획

---

## 8. Changelog

- **v1.0** (2026-06-02): 초안 작성, 5개 벤더 PDF OCR 기반 분석 종합
- **v1.1** (2026-06-04): PDF 원본 재검증 및 수정
  - OCR 오류 정정: SKT A.X K1 파라미터 729B → 519B-A33B (§3.2), NC VARCO "30 에셋" → "3D 에셋" (§4.1)
  - KT 튜토리얼 5번째 항목 미식별 명시 (§1.3)
  - SKT base_url의 `.qa` 도메인 → QA 환경 가능성 표시 (§3.4)
  - 가격 정보 보강: KT 무료(MIT) (§1.3), LG·SKT TBD (§2.3·§3.4), Document Parse 페이지당 모델 안내 (§5.3)
  - PRD 섹션 참조 정정: §5.1 → §5.3 Architecture / §5.4 Pages (§0·§5.6)
  - PHI 격리 원칙 한국 법체계 정합 (§6.2): BAA-equivalent 제거 → PIPA 제26조 처리위탁 + 가명정보 가이드라인 기반
  - 일정 의존성에 대체 시나리오 + 현재 상태 컬럼 추가, 기준일(2026-06-04) 명시 (§6.3)
  - OCR 신뢰도 면책 조항 추가 (문서 헤더)
