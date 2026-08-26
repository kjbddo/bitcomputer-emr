# ValidationAgent Evaluation Report

## 1. Run Metadata

| Item | Value |
|---|---|
| Run ID | `{RUN_ID}` |
| Date | `{DATE}` |
| Agent model | `{AGENT_MODEL}` |
| Max iterations | `{MAX_ITERATIONS}` |
| Scenario files | `{SCENARIO_FILES}` |
| Judge providers | `{JUDGE_PROVIDERS}` |
| Judge prompt version | `{PROMPT_VERSION}` |
| Successful cases | `{SUCCESSFUL_CASES}` |
| Error cases | `{ERROR_CASES}` |

## 1.1 Execution Errors

| Error | Count |
|---|---:|
| `{ERROR_MESSAGE}` | `{ERROR_COUNT}` |

## 2. Dataset Summary

| Category | Count |
|---|---:|
| Normal match | `{NORMAL_MATCH}` |
| X-ray mismatch | `{XRAY_MISMATCH}` |
| Prescription issue | `{PRESCRIPTION_ISSUE}` |
| Insufficient data | `{INSUFFICIENT_DATA}` |
| PubMed needed | `{PUBMED_NEEDED}` |
| Adversarial hallucination | `{ADVERSARIAL}` |

## 3. Tool Call Accuracy

| Metric | Score |
|---|---:|
| Micro Precision | `{MICRO_PRECISION}` |
| Micro Recall | `{MICRO_RECALL}` |
| Micro F1 | `{MICRO_F1}` |
| Macro F1 | `{MACRO_F1}` |
| Average order score | `{AVERAGE_ORDER_SCORE}` |
| Repeat case rate | `{REPEAT_CASE_RATE}` |

### Tool-Level Metrics

| Tool | Precision | Recall | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| X-ray Result Loader | `{XRAY_PRECISION}` | `{XRAY_RECALL}` | `{XRAY_F1}` | `{XRAY_TP}` | `{XRAY_FP}` | `{XRAY_FN}` |
| Disease Validator | `{DISEASE_PRECISION}` | `{DISEASE_RECALL}` | `{DISEASE_F1}` | `{DISEASE_TP}` | `{DISEASE_FP}` | `{DISEASE_FN}` |
| Prescription Validator | `{PRESCRIPTION_VALIDATOR_PRECISION}` | `{PRESCRIPTION_VALIDATOR_RECALL}` | `{PRESCRIPTION_VALIDATOR_F1}` | `{PRESCRIPTION_VALIDATOR_TP}` | `{PRESCRIPTION_VALIDATOR_FP}` | `{PRESCRIPTION_VALIDATOR_FN}` |
| Pubmed Loader | `{PUBMED_PRECISION}` | `{PUBMED_RECALL}` | `{PUBMED_F1}` | `{PUBMED_TP}` | `{PUBMED_FP}` | `{PUBMED_FN}` |
| Prescription Finder | `{PRESCRIPTION_FINDER_PRECISION}` | `{PRESCRIPTION_FINDER_RECALL}` | `{PRESCRIPTION_FINDER_F1}` | `{PRESCRIPTION_FINDER_TP}` | `{PRESCRIPTION_FINDER_FP}` | `{PRESCRIPTION_FINDER_FN}` |

## 4. Hallucination Evaluation

| Metric | Score |
|---|---:|
| Judged cases | `{HALLUCINATION_JUDGED_CASES}` |
| Hallucination rate | `{HALLUCINATION_RATE}` |
| Hallucination detection rate | `{HALLUCINATION_DETECTION_RATE}` |
| Safety pass rate | `{SAFETY_PASS_RATE}` |
| Average claim support | `{AVERAGE_CLAIM_SUPPORT}` |
| Average uncertainty handling | `{AVERAGE_UNCERTAINTY_HANDLING}` |
| Average injection resistance | `{AVERAGE_INJECTION_RESISTANCE}` |

## 5. Judge Agreement

| Agreement Type | Count |
|---|---:|
| Unanimous | `{AGREE_UNANIMOUS}` |
| Majority | `{AGREE_MAJORITY}` |
| Conflict | `{AGREE_CONFLICT}` |
| Judge failed | `{JUDGE_FAILED}` |

## 6. Failure Cases

| Case ID | Category | Failure Type | Notes |
|---|---|---|---|
| `{CASE_ID}` | `{CATEGORY}` | `{FAILURE_TYPE}` | `{NOTES}` |

## 7. Recommended Fixes

- Tool decider prompt 개선:
  - `{TOOL_DECIDER_FIX}`
- Fallback rule 개선:
  - `{FALLBACK_FIX}`
- PubMed query 생성 개선:
  - `{PUBMED_FIX}`
- Hallucination guard 개선:
  - `{HALLUCINATION_GUARD_FIX}`

## 8. Reproducibility Notes

- LLM-as-judge 결과는 정답 label이 아니라 pseudo-gold label이다.
- 평가에 사용한 judge 모델명과 prompt version을 반드시 기록한다.
- PubMed 결과는 시간에 따라 달라질 수 있으므로 결과 캐시 또는 raw response 저장을 권장한다.
- 실제 환자 데이터를 사용할 경우 반드시 익명화한다.
