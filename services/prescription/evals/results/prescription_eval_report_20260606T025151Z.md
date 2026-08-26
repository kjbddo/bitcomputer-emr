# Prescription Agent Evaluation Report

- Generated at: 2026-06-06T03:24:12.635519+00:00
- Raw results: `prescription_eval_results_20260606T025151Z.jsonl`
- Case count: 50
- Successful cases: 11
- Error cases: 39

## Tool Path Metrics

- Precision: 0.890909
- Recall: 1.0
- F1: 0.942308

## Answer Quality

- Judged cases: 11
- Average overall score: 0.409091

## Hallucination

- Judged cases: 11
- Hallucination rate: 0.909091

## By Control Group

- `BASELINE_SAFE`: {'total': 9, 'errors': 6, 'hallucinations': 2}
- `TOOL_PATH`: {'total': 8, 'errors': 6, 'hallucinations': 2}
- `SPARSE_DATA`: {'total': 9, 'errors': 7, 'hallucinations': 2}
- `ADVERSARIAL`: {'total': 9, 'errors': 7, 'hallucinations': 2}
- `HALLUCINATION_TRAP`: {'total': 15, 'errors': 13, 'hallucinations': 2}
