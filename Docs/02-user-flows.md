# 주요 사용자 흐름

이 문서는 사용자가 화면에서 수행하는 이벤트가 어떤 API, 서비스, 저장소를 거쳐 결과로 돌아오는지 설명한다.

## 1. 전체 업무 흐름

```mermaid
flowchart TD
  A[환자 접수] --> B[진료실 입장]
  B --> C[증상/진료 기록 작성]
  C --> D[상병 저장]
  C --> E[처방 저장]
  C --> F[X-ray 이미지 분석]
  D --> G[AI 처방 추천]
  E --> G
  F --> G
  G --> H[검증 에이전트 비동기 실행]
  H --> I[추천 처방/검증 결과 팝업]
  C --> J[진단서 작성]
  J --> K[AI 의사소견 생성]
  J --> L[PDF 다운로드]
  J --> M[DB 저장]
```

## 2. 환자 접수 흐름

```mermaid
sequenceDiagram
  actor User as 원무 사용자
  participant FE as Front-End
  participant Spring as Spring Boot
  participant DB as MySQL

  User->>FE: 환자 정보 입력 후 접수
  FE->>Spring: POST /api/patients/get_patient_id
  Spring->>DB: patient 저장 또는 조회
  DB-->>Spring: patientId
  Spring-->>FE: patientId
  FE->>Spring: POST /api/waiting/register
  Spring->>DB: waiting 등록
  Spring-->>FE: 접수 결과 / 토큰
  FE-->>User: 대기 목록 갱신
```

주요 데이터:

- `patient`: 환자 기본 정보
- `waiting`: 대기 상태
- `employee`, `dept`: 담당자/부서 정보

## 3. 진료실 상병/처방 저장 흐름

```mermaid
sequenceDiagram
  actor Doctor as 의료진
  participant FE as Front-End
  participant Spring as Spring Boot
  participant DB as MySQL

  Doctor->>FE: 증상 작성, 상병/처방 선택
  FE->>Spring: POST /api/histories/write_history
  Spring->>DB: history 저장
  Spring-->>FE: historyId
  FE->>Spring: PUT /api/histories/{historyId}/set_diseases
  Spring->>DB: history_disease 저장
  FE->>Spring: PUT /api/histories/{historyId}/set_diagnoses
  Spring->>DB: history_diagnose 저장
  Spring-->>FE: 저장 완료
```

상병과 처방은 마스터 테이블의 원본을 그대로 참조하기보다, 진료 시점의 스냅샷을 `history_disease`, `history_diagnose`에 저장하는 구조다.

## 4. X-ray 이미지 분석 흐름

```mermaid
sequenceDiagram
  actor Doctor as 의료진
  participant FE as AIReport
  participant Spring as Spring Boot
  participant Xray as XrayGraphRAG
  participant Arango as ArangoDB
  participant Files as Image Volume
  participant DB as MySQL

  Doctor->>FE: 이미지 업로드, AP/PA 선택, AI 분석 클릭
  FE->>Spring: POST /api/radiology/upload-and-analyze multipart
  Spring->>Files: 이미지 저장
  Spring->>DB: radiology_report 초기 행 저장
  Spring->>Xray: POST /infer image + view + topK
  Xray->>Arango: 유사 case 벡터 검색
  Xray->>Arango: 그래프 근거 조회
  Xray->>Files: heatmap 저장
  Xray-->>Spring: predictedDiseases, heatmapUrl, warning
  Spring->>DB: radiology_report 결과 갱신
  Spring-->>FE: 분석 결과
  FE-->>Doctor: 상위 3개 상병 후보와 히트맵 표시
```

프론트 표시는 `predictedDiseases`를 점수 기준 정렬한 뒤 `no_finding`, `support_devices` 등 상병이 아닌 태그를 제외하고 최대 3개만 보여준다.

## 5. AI 처방 추천 및 검증 흐름

처방 추천 버튼은 단순 추천 API 호출이 아니라 검증 job을 시작한다. 추천 후보, 저장 상병/처방, X-ray 추론, PubMed 근거를 함께 검토한다.

```mermaid
sequenceDiagram
  actor Doctor as 의료진
  participant FE as Diagnosis
  participant Spring as Spring Boot
  participant DB as MySQL
  participant RMQ as RabbitMQ
  participant Val as ValidationAgent
  participant Rx as Prescription API
  participant PubMed as PubMed

  Doctor->>FE: AI 처방 추천 클릭
  FE->>Spring: POST /api/agent/prescription/recommend
  Spring->>DB: validation_job PENDING 생성
  Spring->>RMQ: validation.prescription.request 발행
  Spring-->>FE: jobId 반환

  loop 2초 간격 polling
    FE->>Spring: GET /api/validation-jobs/{jobId}
    Spring->>DB: validation_job/result 조회
    Spring-->>FE: PENDING/RUNNING/DONE/FAILED
  end

  RMQ-->>Val: request consume
  Val->>RMQ: RUNNING 결과 발행
  Val->>Rx: Prescription Finder 호출
  Val->>PubMed: Pubmed Loader 검색
  Val->>RMQ: DONE/FAILED 결과 발행
  RMQ-->>Spring: result consume
  Spring->>DB: validation_result 저장, validation_job DONE
  FE-->>Doctor: 검증 요약, 이유, PubMed 근거, 추천 처방 표시
```

상태:

- `PENDING`: Spring이 job을 만들고 큐에 넣은 상태
- `RUNNING`: ValidationAgent가 메시지를 소비하고 처리 중
- `DONE`: 검증 결과 저장 완료
- `FAILED`: 처리 실패

## 6. 진단서 생성, PDF, DB 저장 흐름

진단서 화면은 PDF 위에 입력을 얹는 방식이 아니라, PNG 템플릿 배경 위에 HTML 입력 필드를 배치한다. 다운로드는 브라우저에서 `html2canvas`와 `pdf-lib`를 이용해 PDF로 변환한다.

```mermaid
sequenceDiagram
  actor User as 사용자
  participant FE as MedicalCertificate
  participant Spring as Spring Boot
  participant Cert as Certificate API
  participant Gemini as Gemini
  participant DB as MySQL
  participant Files as Certificate Storage

  User->>FE: 환자 조회, 상병 적용
  User->>FE: AI 생성 클릭
  FE->>Spring: POST /api/agent/document/generate
  Spring->>DB: history, patient, disease, diagnose 조회
  Spring->>Cert: POST /api/ai/document/generate
  Cert->>Gemini: 진단서 소견 생성
  Gemini-->>Cert: 치료 내용 및 향후 치료 소견
  Cert-->>Spring: medicalCertificate
  Spring-->>FE: medicalCertificate + token
  FE-->>User: 미리보기 모달
  User->>FE: 수락 또는 거절

  alt PDF 다운로드
    User->>FE: PDF 다운로드 클릭
    FE->>FE: DOM 캡처 후 PDF Blob 생성
    FE-->>User: 로컬 PDF 다운로드
  else DB 저장
    User->>FE: 저장 클릭
    FE->>FE: 현재 진단서 DOM을 PDF Blob으로 변환
    FE->>Spring: POST /api/agent/document/save multipart
    Spring->>Files: PDF 저장
    Spring->>DB: medical_certificate 저장
    Spring-->>FE: 저장 완료 + token
  end
```

진단서 저장 시 저장되는 내용:

- `historyId`
- PDF 파일 경로
- AI 사용 여부
- AI 원문 소견
- 최종 저장 소견
- 피드백 타입: `APPROVE`, `MODIFY`, `REJECT`, `NONE`

## 7. 실패와 폴백 흐름

```mermaid
flowchart TD
  A[AI 요청] --> B{외부 AI 성공?}
  B -->|예| C[AI 결과 반환]
  B -->|아니오| D{기능별 폴백 존재?}
  D -->|진단서| E[백엔드 기본 소견 템플릿 반환]
  D -->|검증 에이전트| F[규칙 기반 tool decision / rule finalize]
  D -->|XrayGraphRAG| G[Mock 모델 또는 brute-force 검색 fallback]
  D -->|없음| H[오류 응답]
```

중요한 점은 폴백 결과도 최종 의료 판단이 아니라 의료진 검토용 보조 정보라는 점이다.
