#!/usr/bin/env python3
"""흔한 상병에 대한 합성 진료 케이스를 만들어 그래프 적재 CSV 로 낸다.

왜 필요한가
-----------
엑셀 원본에서 나온 그래프에는 **상병이 9개뿐**이다(A15 C34 D50 E03 E11 E78
I10 J18 J90). 처방 추천의 코호트 조회는 상병 코드로 같은 상병 방문들의 처방을
모으므로, 그 9개 밖의 상병을 고르면 후보가 언제나 0건이다. 화면에서는 "우리
데이터가 뒷받침하는 처방 후보가 0건" 으로 정직하게 나오지만, 감기·위염처럼
일상적인 상병조차 답이 없으면 기능이 있는지 확인할 방법이 없다.

무엇을 만드는가
---------------
아래 `CASE_TEMPLATES` 의 상병마다 방문을 여러 건 만들고, 그 방문에 약제
처방 라인을 붙인다. **약제 코드는 지어내지 않는다** — 원본 엑셀에서 나온
`output/03_prescription_master_nodes.csv` 에 실제로 있는 9자리 EDI 코드만
쓴다. 상병-약 조합만 합성이고, 약 자체는 이 병원 데이터에 실재하던 것이다.

합성임을 숨기지 않는다
----------------------
- 방문 `_key` 는 `VISIT_SYN...` 으로 시작한다. 원본은 `VISIT_<내원번호>` 다
- 방문 문서에 `source="synthetic"` 과 `generated_by` 를 남긴다
- 처방 라인 `_key` 는 `OL_SYN...` 이다

원본과 섞여도 어느 것이 만들어진 것인지 언제든 가려낼 수 있어야 한다.
가려낼 수 없으면, 나중에 "우리 데이터가 이렇게 말한다" 는 문장이 무엇을
근거로 한 것인지 아무도 답할 수 없게 된다.

결정론
------
같은 입력에서 같은 CSV 가 나온다. 난수를 쓰지 않고 템플릿과 인덱스로만
방문을 만든다 — 다시 돌렸을 때 `_key` 가 달라지면 `--append` 적재가 코퍼스를
복제한다(seed_chexpert.py 가 같은 이유로 573건이 된 적이 있다).

실행
----
    python make_synthetic_cases.py                 # output_synthetic/ 에 CSV 생성
    python make_synthetic_cases.py --check         # 약제 코드가 실재하는지만 확인
    python import_to_arango.py --output-dir output_synthetic --append
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
MASTER_CSV = SCRIPT_DIR / "output" / "03_prescription_master_nodes.csv"
DEFAULT_OUT = SCRIPT_DIR / "output_synthetic"

# 9자리 정확히 = 약제. services/prescription/medication_codes.py 와 같은 규칙이다.
MEDICATION_CODE = re.compile(r"^\d{9}$")


# 상병별 처방 템플릿.
#
# 각 항목은 (상병코드, 상병설명, [(약제코드, 1회용량, 1일횟수, 투약일수), ...]).
# 약제 조합은 국내 1차 진료에서 흔한 형태를 따르되, **코드는 전부 원본
# 마스터에 실재하는 것**이다(--check 가 이것을 강제한다).
#
# 용량·횟수·일수를 넣는 이유: order_lines 가 그 값을 들고 있어야 추천이
# "무엇을 얼마나" 까지 말할 수 있다. 값이 없으면 코드만 나열하게 된다.
CASE_TEMPLATES: List[Tuple[str, str, List[Tuple[str, str, int, int]]]] = [
    ("J00", "급성 비인두염(감기)", [
        ("672300240", "1정", 3, 3),   # 타이레놀8시간이알서방정(아세트아미노펜)
        ("642102570", "1정", 3, 3),   # 페니라민정
        ("646001150", "1캡슐", 3, 3),  # 뮤코스텐캡슐(아세틸시스테인)
    ]),
    ("J20", "급성 기관지염", [
        ("643303130", "1캡슐", 3, 5),  # 종근당아목시실린캡슐500mg
        ("650203656", "10mL", 3, 5),   # 시네츄라시럽
        ("628900110", "1정", 3, 5),    # 이든암브록솔염산염정
    ]),
    ("J45", "천식", [
        ("055102870", "1정", 1, 28),   # 몬테레진정(몬테루카스트/레보세티리진)
        ("671800510", "1정", 2, 14),   # 대원아미노필린정
    ]),
    ("K21", "위-식도역류병", [
        ("628900520", "1정", 1, 14),   # 에소프라정20mg(에스오메프라졸)
        ("643500520", "1정", 3, 14),   # 레마이드정100mg(레바미피드)
    ]),
    ("K29", "위염 및 십이지장염", [
        ("693902610", "1정", 1, 14),   # 판토라정20mg(판토프라졸)
        ("644802781", "15mL", 3, 7),   # 파티겔현탁액(알마게이트)
        ("622803730", "1정", 3, 14),   # 모사프리엠정(모사프리드)
    ]),
    ("M54", "등통증", [
        ("622801610", "1정", 2, 5),    # 락소펜엠정(록소프로펜)
        ("642301360", "1정", 3, 5),    # 삼성바클로펜정
    ]),
    ("L20", "아토피성 피부염", [
        ("628902170", "1정", 1, 14),   # 이포산서방정(베포타스틴)
        ("641704511", "적당량", 2, 14),  # 프리베이트크림(프레드니카르베이트)
    ]),
    ("I20", "협심증", [
        ("641100270", "1정", 1, 30),   # 아스피린프로텍트정100mg
        ("628900450", "1정", 1, 30),   # 리피엔정20mg(아토르바스타틴)
    ]),
    ("H10", "결막염", [
        ("653603051", "1방울", 4, 7),   # 파타놀점안액0.1%(올로파타딘)
    ]),
    ("N39", "요로계통의 기타 장애", [
        ("645401870", "1정", 1, 5),    # 크라비트정500mg(레보플록사신)
    ]),
]

# 상병 하나당 만들 방문 수.
#
# 코호트 조회는 빈도로 순위를 매기므로, 방문이 1건이면 모든 약이 같은 빈도가
# 되어 순위가 무의미해진다. 12건이면 아래 VARIATIONS 의 생략 규칙이 약마다
# 다른 빈도를 만들어 순위가 실제로 갈린다.
VISITS_PER_DIAGNOSIS = 12

# 방문마다 처방을 조금씩 달리한다.
#
# 모든 방문이 템플릿 전체를 그대로 받으면 빈도가 전부 같아져 추천 순위가
# 입력 순서로 결정된다. 그러면 "코호트에서 자주 쓰였다" 는 근거 문장이 실제로
# 아무것도 뜻하지 않게 된다. 뒤쪽 약일수록 자주 빠지게 해서 1차 약제가 위로
# 오도록 한다 — 임상적으로도 그 순서가 맞다.
def _lines_for_visit(drugs: List[Tuple[str, str, int, int]], index: int):
    out = []
    for position, drug in enumerate(drugs):
        # position 0(1차 약제)은 항상, 뒤로 갈수록 건너뛰는 방문이 늘어난다.
        if position == 0 or index % (position + 1) != 0:
            out.append(drug)
    return out


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def load_master_names() -> Dict[str, str]:
    if not MASTER_CSV.exists():
        sys.exit(f"[fail] 처방 마스터를 찾을 수 없습니다: {MASTER_CSV}")
    with MASTER_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {
            row["prescription_code"]: row["canonical_name"]
            for row in csv.DictReader(fh)
        }


def check_codes(names: Dict[str, str]) -> int:
    """템플릿의 약제 코드가 전부 실재하고 9자리인지 확인한다.

    지어낸 코드가 섞이면 추천이 존재하지 않는 약을 제시하게 된다. 그건 이
    시스템이 가장 하면 안 되는 종류의 오류다.
    """
    problems = []
    for code_dx, label, drugs in CASE_TEMPLATES:
        for code, *_ in drugs:
            if not MEDICATION_CODE.match(code):
                problems.append(f"{code_dx} {code}: 9자리 약제 코드가 아니다")
            elif code not in names:
                problems.append(f"{code_dx} {code}: 처방 마스터에 없다")
    for line in problems:
        print(f"  [fail] {line}")
    if problems:
        return 1
    total = sum(len(d) for _, _, d in CASE_TEMPLATES)
    print(f"  [ok] 상병 {len(CASE_TEMPLATES)}개 / 약제 코드 {total}개 모두 마스터에 실재")
    for code_dx, label, drugs in CASE_TEMPLATES:
        print(f"    {code_dx} {label}")
        for code, dose, freq, days in drugs:
            print(f"       {code}  {names[code][:46]}  {dose} x{freq} {days}일")
    return 0


def build_rows(names: Dict[str, str]):
    visits, dx_nodes, order_lines = [], [], []
    e_visit_dx, e_visit_order, e_order_rx, e_order_dx = [], [], [], []

    for code_dx, label, drugs in CASE_TEMPLATES:
        dx_nodes.append({"diagnosis_code": code_dx, "상병코드_norm": code_dx})
        for index in range(VISITS_PER_DIAGNOSIS):
            visit_id = f"VISIT_SYN{_key(code_dx, str(index))}"
            visits.append({
                "visit_id": visit_id,
                "내원번호_norm": "",
                # 합성임을 문서 자체가 말한다. 이 표시가 없으면 원본 진료
                # 기록과 구분할 방법이 사라진다.
                "source": "synthetic",
                "generated_by": "make_synthetic_cases.py",
                "synthetic_diagnosis": code_dx,
                "synthetic_label": label,
            })
            e_visit_dx.append({"visit_id": visit_id, "diagnosis_code": code_dx})

            for seq, (code, dose, freq, days) in enumerate(_lines_for_visit(drugs, index), start=1):
                order_id = f"OL_SYN{_key(visit_id, code)}"
                order_lines.append({
                    "order_line_id": order_id,
                    "visit_id": visit_id,
                    "처방시퀀스_norm": seq,
                    "처방코드_norm": code,
                    "prescription_code": code,
                    "처방명_norm": names[code],
                    "1회투약량": dose,
                    "1일투여횟수": freq,
                    "총투약일수": days,
                    "source": "synthetic",
                })
                e_visit_order.append({"visit_id": visit_id, "order_line_id": order_id})
                e_order_rx.append({"order_line_id": order_id, "prescription_code": code})
                e_order_dx.append({"order_line_id": order_id, "diagnosis_code": code_dx})

    return {
        "01_visit_nodes.csv": visits,
        "02_diagnosis_nodes.csv": dx_nodes,
        "04_order_line_nodes.csv": order_lines,
        "11_rel_visit_has_diagnosis.csv": e_visit_dx,
        "12_rel_visit_has_order.csv": e_visit_order,
        "13_rel_order_refers_to_prescription.csv": e_order_rx,
        "15_rel_order_associated_with_diagnosis.csv": e_order_dx,
    }


def write_csvs(out_dir: Path, tables, names: Dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 처방 마스터는 원본을 그대로 복사한다. 합성 처방이 참조하는 코드가 전부
    # 여기 있어야 order_refers_prescription 간선이 끊기지 않는다.
    used = sorted({row["prescription_code"] for row in tables["04_order_line_nodes.csv"]})
    master_rows = [
        {"prescription_code": code, "canonical_name": names[code],
         "name_variant_count": 1, "review_flag": False}
        for code in used
    ]
    tables = dict(tables)
    tables["03_prescription_master_nodes.csv"] = master_rows

    # import_to_arango.py 가 없으면 건너뛰는 선택 파일들. 빈 파일로 두면
    # "특이사항이 없다" 가 아니라 "이 세트는 특이사항을 만들지 않는다" 로
    # 읽히도록 헤더만 남긴다.
    tables["05_special_note_nodes.csv"] = []
    tables["14_rel_visit_has_note.csv"] = []

    headers = {
        "05_special_note_nodes.csv": ["note_id", "visit_id", "특이사항_norm"],
        "14_rel_visit_has_note.csv": ["visit_id", "note_id"],
    }

    for filename, rows in sorted(tables.items()):
        path = out_dir / filename
        cols = list(rows[0].keys()) if rows else headers[filename]
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  {filename:44} {len(rows):5}행")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true",
                    help="약제 코드가 처방 마스터에 실재하는지만 확인하고 끝낸다")
    args = ap.parse_args()

    names = load_master_names()
    if args.check:
        return check_codes(names)

    rc = check_codes(names)
    if rc:
        return rc
    print()
    tables = build_rows(names)
    write_csvs(args.out_dir.resolve(), tables, names)
    print()
    print(f"  적재: python import_to_arango.py --output-dir {args.out_dir} --append")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
