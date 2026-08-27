# Prescription Agent Evaluation Report

- Generated at: 2026-06-06T04:03:30.482126+00:00
- Raw results: `prescription_eval_results_20260606T034823Z.jsonl`
- Case count: 50
- Successful cases: 50
- Error cases: 0

## Tool Path Metrics

- Precision: 0.874439
- Recall: 0.979899
- F1: 0.924171

## Answer Quality

- Judged cases: 50
- Average overall score: 0.386

## Hallucination

- Judged cases: 50
- Hallucination rate: 0.9

## By Control Group

- `BASELINE_SAFE`: {'total': 9, 'errors': 0, 'hallucinations': 4}
- `TOOL_PATH`: {'total': 8, 'errors': 0, 'hallucinations': 8}
- `SPARSE_DATA`: {'total': 9, 'errors': 0, 'hallucinations': 9}
- `ADVERSARIAL`: {'total': 9, 'errors': 0, 'hallucinations': 9}
- `HALLUCINATION_TRAP`: {'total': 15, 'errors': 0, 'hallucinations': 15}

## Analysis

The HTTP API run completed without transport or schema errors. Tool tracing was collected for all 50 cases, and the core pipeline steps (`prompt_builder`, `llm_generate`, `json_parse`) were stable.

The main risk is answer grounding. The average answer quality score was 0.386 and the hallucination rate was 0.9, which is far below the intended operating threshold. The most frequent failure pattern was generating prescriptions, codes, or dosage details that were not anchored in `top_rx`, ArangoDB, cohort output, or the scenario evidence.

Observed issue counts from the raw result file:

- Answer quality issues: `UNSUPPORTED_REASON` 102, `UNANCHORED_NAME` 41, `CODE_MISMATCH` 25, `DOSAGE_FABRICATION` 11.
- Hallucination types: `UNANCHORED_PRESCRIPTION` 43, `FAKE_CODE` 43, `DOSAGE_FABRICATION` 43, `UNSUPPORTED_HISTORY` 28, `PROMPT_INJECTION_FOLLOWED` 26, `OVERCONFIDENT_RECOMMENDATION` 23, `UNSUPPORTED_ACTION` 22.

## Recommendations

- Strengthen the prescription prompt so the model must not generate prescription names, codes, or dosages outside the provided evidence.
- Add a post-processing guard in `prescription_api.py` that removes or downgrades unanchored recommendations.
- Allow a structured “insufficient evidence” response instead of forcing Top-3 recommendations when `top_rx` and cohort evidence are sparse.
- Reconcile the `confidence_scores` expected path policy because the current implementation computes it broadly when `disease_codes` exist, while several scenarios judge it as unnecessary.
- Freeze sparse, adversarial, and hallucination trap failures as a regression set before the next prompt or guard change.
