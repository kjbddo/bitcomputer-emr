# Prescription Agent Evaluation Report

- Generated at: 2026-06-06T03:46:52.033890+00:00
- Raw results: `prescription_eval_results_20260606T033259Z.jsonl`
- Case count: 50
- Successful cases: 47
- Error cases: 3

## Tool Path Metrics

- Precision: 0.867925
- Recall: 0.978723
- F1: 0.92

## Answer Quality

- Judged cases: 47
- Average overall score: 0.379787

## Hallucination

- Judged cases: 47
- Hallucination rate: 0.893617

## By Control Group

- `BASELINE_SAFE`: {'total': 9, 'errors': 0, 'hallucinations': 4}
- `TOOL_PATH`: {'total': 8, 'errors': 1, 'hallucinations': 7}
- `SPARSE_DATA`: {'total': 9, 'errors': 1, 'hallucinations': 8}
- `ADVERSARIAL`: {'total': 9, 'errors': 1, 'hallucinations': 8}
- `HALLUCINATION_TRAP`: {'total': 15, 'errors': 0, 'hallucinations': 15}
