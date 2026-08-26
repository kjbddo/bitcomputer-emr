# ValidationAgent 평가 도구

이 폴더는 `ValidationAgent`의 tool 호출 정확도와 환각 대응 능력을 평가하기 위한 입력 데이터, judge 프롬프트, 실행 스크립트, 리포트 템플릿을 담는다.

## 구성

- `schemas/scenario.schema.json`: JSONL scenario 한 줄의 스키마.
- `scenarios/*.jsonl`: synthetic/adversarial 평가 케이스.
- `prompts/*.md`: tool-call judge, adjudicator, hallucination judge 프롬프트.
- `generate_scenarios.py`: synthetic/adversarial/mixed 평가 케이스 JSONL 생성기.
- `run_eval.py`: 에이전트 실행, judge 호출, metric 계산, 리포트 생성을 수행하는 CLI.
- `report_template.md`: 최종 평가 리포트 양식.

## 빠른 실행

처음 로컬에서 실행한다면 먼저 의존성을 설치한다.

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\ValidationAgent"
python -m pip install -r .\requirements.txt
```

`evals/.env`, `ValidationAgent/.env`, 프로젝트 루트의 `.env.docker`는 자동으로 로드된다. 추가 env 파일은 `--env-file`로 넘길 수 있다.

## 테스트 데이터 생성

초기 수동 샘플은 `scenarios/synthetic_tool_scenarios.jsonl`, `scenarios/adversarial_hallucination_scenarios.jsonl`에 들어 있다. 대량 테스트 데이터는 `generate_scenarios.py`로 생성한다.

기본 데이터 생성은 `--strategy llm`을 사용한다. ValidationAgent가 OpenAI `gpt-5-nano`를 쓰는 경우, 테스트 데이터 생성은 같은 모델을 피하고 `--provider gemini` 또는 `--provider anthropic`처럼 독립 모델을 사용한다. 이 방식은 평가 대상 모델이 직접 만든 패턴에 과적합되는 것을 줄이기 위한 목적이다.

Gemini로 50개 mixed 케이스 생성:

```powershell
python .\evals\generate_scenarios.py --strategy llm --provider gemini --model gemini-2.0-flash --mode mixed --count 50 --output .\evals\scenarios\llm_generated_mixed_scenarios.jsonl
```

Gemini quota가 부족하면 ValidationAgent의 `gpt-5-nano`와 다른 모델인 `gpt-4o-mini`로도 생성할 수 있다.

```powershell
python .\evals\generate_scenarios.py --strategy llm --provider openai --model gpt-4o-mini --mode mixed --count 30 --output .\evals\scenarios\llm_generated_mixed_scenarios.jsonl
```

tool-call 중심 synthetic 케이스만 LLM으로 생성:

```powershell
python .\evals\generate_scenarios.py --strategy llm --provider gemini --model gemini-2.0-flash --mode synthetic --count 50 --output .\evals\scenarios\llm_generated_synthetic_tool_scenarios.jsonl
```

hallucination/prompt-injection 중심 adversarial 케이스만 LLM으로 생성:

```powershell
python .\evals\generate_scenarios.py --strategy llm --provider gemini --model gemini-2.0-flash --mode adversarial --count 30 --output .\evals\scenarios\llm_generated_adversarial_scenarios.jsonl
```

생성된 데이터로 평가 실행:

```powershell
python .\evals\run_eval.py --scenarios .\evals\scenarios\llm_generated_mixed_scenarios.jsonl --output-dir .\evals\results --skip-judges --disable-agent-llm
```

재현성이 더 중요한 smoke/regression 데이터가 필요하면 LLM 없이 template 기반으로도 생성할 수 있다.

```powershell
python .\evals\generate_scenarios.py --strategy template --mode mixed --count 50 --output .\evals\scenarios\template_generated_mixed_scenarios.jsonl
```

LLM 생성에는 `prompts/llm_scenario_generator.md`가 사용된다. `prompts/adversarial_generator.md`는 adversarial 케이스만 별도로 만들 때 참고할 수 있는 프롬프트다.

현재 생성해 둔 LLM 기반 평가 데이터:

- `scenarios/llm_generated_mixed_scenarios.jsonl`: `gpt-4o-mini`로 생성한 30개 mixed 케이스. `NORMAL_MATCH`, `XRAY_MISMATCH`, `UNRELATED_PRESCRIPTION`, `INSUFFICIENT_DATA`, `LITERATURE_NEEDED`, `PROMPT_INJECTION`, `FAKE_PUBMED`, `FAKE_DRUG`, `XRAY_CONFLICT`, `OVERCONFIDENT_DIAGNOSIS`를 각각 3개씩 포함한다.

## 평가 실행

외부 judge API 없이 에이전트만 실행하고 rule 기반 metric만 확인:

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\ValidationAgent"
python .\evals\run_eval.py --scenarios .\evals\scenarios\synthetic_tool_scenarios.jsonl --output-dir .\evals\results --skip-judges
```

LLM 호출 없이 fallback tool rule만 빠르게 확인:

```powershell
python .\evals\run_eval.py --scenarios .\evals\scenarios\synthetic_tool_scenarios.jsonl --output-dir .\evals\results --skip-judges --disable-agent-llm --limit 2
```

OpenAI judge까지 사용:

```powershell
$env:OPENAI_API_KEY="..."
python .\evals\run_eval.py --scenarios .\evals\scenarios\synthetic_tool_scenarios.jsonl --output-dir .\evals\results --judge-provider openai --openai-judge-model gpt-5.4-mini
```

Gemini/Claude judge는 `--judge-provider gemini` 또는 `--judge-provider anthropic`을 함께 지정할 수 있다. 각각 `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`가 필요하다.
