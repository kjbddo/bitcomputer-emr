"""CheXpert v1.0(small) 데이터셋을 XrayGraphRAG 형식으로 변환·등록한다.

CSV 형식(첫 줄):
  Path,Sex,Age,Frontal/Lateral,AP/PA,No Finding,Enlarged Cardiomediastinum,Cardiomegaly,
  Lung Opacity,Lung Lesion,Edema,Consolidation,Pneumonia,Atelectasis,Pneumothorax,
  Pleural Effusion,Pleural Other,Fracture,Support Devices

라벨 값: 1.0=positive, 0.0=negative, -1.0=uncertain, 빈칸=unmentioned
Path 예: "CheXpert-v1.0-small/valid/patient64541/study1/view1_frontal.jpg" → archive 안 실제 파일은
        archive/valid/patient64541/study1/view1_frontal.jpg

실행:
  # 0) ArangoDB 띄우기
  cd XrayGraphRAG && docker compose up -d arangodb

  # 1) 스키마 초기화 (한 번만)
  python scripts/init_db.py

  # 2) valid 234건만 빠르게 등록 (frontal AP/PA 만)
  python scripts/seed_chexpert.py --split valid --frontal-only

  # 3) train 부분 등록(예: 200장, frontal only, U-Ones 정책)
  python scripts/seed_chexpert.py --split train --frontal-only --limit 200 --uncertainty ones

  # 4) 변환 결과 미리보기 (ArangoDB 호출 없음)
  python scripts/seed_chexpert.py --split valid --dry-run --limit 3

옵션:
  --archive PATH      CheXpert archive 루트 (default: C:/Users/kjbdd/Downloads/archive)
  --split {valid,train}  default: valid
  --limit N           처리할 최대 행 수
  --frontal-only      Frontal 만 등록 (Lateral 제외)
  --view {AP,PA}      AP/PA 컬럼 기준 특정 view 만 등록
  --uncertainty {ones,zeros,ignore}  -1.0 처리 정책 (default: ones)
  --include-no-finding  No Finding=1 인 case 도 등록 (default: 등록 O, 단 disease tags 빈 리스트)
  --batch N           N건 마다 진행 출력 (default: 25)
  --max-per-disease N disease 별 최대 등록 수 (균형 표본용; 0 이면 무제한)
  --use-real-model    USE_TORCH_ANOMALY 강제 ON (SQUID 어댑터로 실제 reconstruction)
  --reset             적재 전에 케이스와 간선을 비움 (분류 체계는 보존)
  --dry-run           라벨 변환 결과만 출력

재실행에 대하여:
  케이스 _key 를 CSV 의 Path 에서 유도하므로 **같은 원본은 같은 케이스로
  덮어써진다.** 같은 명령을 두 번 돌려도 건수가 늘지 않는다.

  --reset 은 그와 별개다. 대상 범위를 좁히거나(--limit, --max-per-disease)
  정책을 바꿔 적재할 때, 이전 실행이 남긴 **범위 밖 케이스**는 덮어쓰기로는
  사라지지 않는다. 코퍼스를 그 실행의 결과와 정확히 일치시키려면 --reset 을
  쓴다.

  분할기를 바꿨을 때(USE_PSPNET_ROI 등)는 반드시 전량 재적재해야 한다.
  마스크가 달라지면 저장된 ROI 임베딩과 질의가 서로 다른 해부 기준을 비교하게
  된다. 요약의 roiMaskVersion 이 한 종류인지 확인할 것.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def _setup_io() -> None:
    for s in ("stdout", "stderr"):
        try:
            getattr(sys, s).reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    here = Path(__file__).resolve()
    if str(here.parent.parent) not in sys.path:
        sys.path.insert(0, str(here.parent.parent))


_setup_io()


# ---------- 라벨 매핑 ----------
# CheXpert CSV 컬럼명 → 시스템 disease tag _key
CHEXPERT_LABELS: List[Tuple[str, str]] = [
    ("Enlarged Cardiomediastinum", "enlarged_cardiomediastinum"),
    ("Cardiomegaly", "cardiomegaly"),
    ("Lung Opacity", "lung_opacity"),
    ("Lung Lesion", "lung_lesion"),
    ("Edema", "edema"),
    ("Consolidation", "consolidation"),
    ("Pneumonia", "pneumonia"),
    ("Atelectasis", "atelectasis"),
    ("Pneumothorax", "pneumothorax"),
    ("Pleural Effusion", "pleural_effusion"),
    ("Pleural Other", "pleural_other"),
    ("Fracture", "fracture"),
]


def parse_label(value: str) -> Optional[float]:
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def row_to_disease_tags(row: Dict[str, str], uncertainty: str) -> List[str]:
    """CheXpert row → disease tag 리스트.

    - 1.0  : positive (등록)
    - 0.0  : negative (제외)
    - -1.0 : uncertain
        * uncertainty='ones': positive 처리
        * uncertainty='zeros': negative 처리
        * uncertainty='ignore': skip (해당 라벨 무시; 다른 라벨엔 영향 없음)
    - 빈값 : unmentioned (제외)
    """
    no_finding = parse_label(row.get("No Finding", ""))
    if no_finding == 1.0:
        return []  # 정상

    tags: List[str] = []
    for col, key in CHEXPERT_LABELS:
        v = parse_label(row.get(col, ""))
        if v == 1.0:
            tags.append(key)
        elif v == -1.0:
            if uncertainty == "ones":
                tags.append(key)
            elif uncertainty == "zeros":
                pass
            else:  # ignore
                pass
    return tags


def resolve_image_path(archive: Path, csv_path: str) -> Path:
    """CSV의 Path("CheXpert-v1.0-small/valid/...") 를 archive 안 실제 파일 경로로 매핑."""
    csv_path = csv_path.strip().replace("\\", "/")
    prefix = "CheXpert-v1.0-small/"
    if csv_path.startswith(prefix):
        rel = csv_path[len(prefix):]
    else:
        rel = csv_path
    return archive / rel


def iter_rows(csv_file: Path) -> Iterable[Dict[str, str]]:
    with open(csv_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


# ---------- 메인 ----------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=str, default=r"C:\Users\kjbdd\Downloads\archive")
    parser.add_argument("--split", choices=["valid", "train"], default="valid")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--frontal-only", action="store_true")
    parser.add_argument("--view", choices=["AP", "PA"], default=None,
                        help="AP/PA 컬럼 기준 특정 view 만 등록합니다. 예: --view PA")
    parser.add_argument("--uncertainty", choices=["ones", "zeros", "ignore"], default="ones")
    parser.add_argument("--include-no-finding", action="store_true",
                        help="default 도 등록함. 비활성화하려면 --skip-no-finding 사용")
    parser.add_argument("--skip-no-finding", action="store_true")
    parser.add_argument("--batch", type=int, default=25)
    parser.add_argument("--max-per-disease", type=int, default=0)
    parser.add_argument("--use-real-model", action="store_true")
    parser.add_argument("--reset", action="store_true",
                        help="적재 전에 케이스와 그 간선을 모두 비웁니다. "
                             "분류 체계(diseases/findings/rois)는 건드리지 않습니다.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    archive = Path(args.archive)
    if not archive.exists():
        print(f"[fail] archive not found: {archive}")
        return 2
    csv_file = archive / f"{args.split}.csv"
    if not csv_file.exists():
        print(f"[fail] csv not found: {csv_file}")
        return 2

    if args.use_real_model:
        os.environ["USE_TORCH_ANOMALY"] = "true"

    # 환경 정보
    print(f"[info] archive={archive}")
    print(f"[info] split={args.split} csv={csv_file}")
    print(f"[info] uncertainty policy={args.uncertainty} frontal_only={args.frontal_only} view={args.view or 'all'}")
    if args.dry_run:
        print("[info] DRY-RUN: 라벨 변환만 출력합니다 (DB / 모델 호출 없음)")

    # ------------- DRY RUN -------------
    if args.dry_run:
        n = 0
        per_disease: Counter[str] = Counter()
        for row in iter_rows(csv_file):
            if args.frontal_only and row.get("Frontal/Lateral", "") != "Frontal":
                continue
            if args.view and row.get("AP/PA", "") != args.view:
                continue
            tags = row_to_disease_tags(row, args.uncertainty)
            if not tags and (args.skip_no_finding or not args.include_no_finding):
                # default: include_no_finding=True로 동작; 명시적 skip 만 제외
                if args.skip_no_finding:
                    continue
            full_path = resolve_image_path(archive, row["Path"])
            ok = full_path.exists()
            n += 1
            per_disease.update(tags or ["__no_finding__"])
            if n <= (args.limit or 5):
                print(f"  [{n:>4}] {row['Path']}")
                print(f"         exists={ok} view={row.get('AP/PA','-')} sex={row.get('Sex','-')} "
                      f"age={row.get('Age','-')} → tags={tags}")
            if args.limit and n >= args.limit:
                break
        print()
        print(f"[summary] rows: {n}")
        print(f"[summary] disease distribution (top):")
        for k, v in per_disease.most_common(20):
            print(f"   {k:35s}  {v}")
        return 0

    # ------------- LIVE 등록 -------------
    # 컨테이너 lazy import (ArangoDB 미실행 시 에러를 여기서 명확히 노출)
    from app.env_check import require_env

    require_env(["ARANGO_PASSWORD"])

    try:
        from app.api.dependencies import get_container
    except Exception as e:
        print(f"[fail] failed to build service container: {e}")
        return 3

    try:
        container = get_container()
    except Exception as e:
        print(f"[fail] ArangoDB 연결 실패: {e}")
        print("       docker compose up -d arangodb 후 init-db 가 끝났는지 확인하세요.")
        return 3

    case_service = container.case_service
    from app.models.schemas import CaseRegisterMetadata  # noqa: E402
    from app.utils.id_utils import case_key_for_source  # noqa: E402

    if args.reset:
        removed = container.repo.reset_cases()
        total = sum(removed.values())
        print(f"[reset] 케이스·간선 {total}건 삭제: "
              + ", ".join(f"{k}={v}" for k, v in removed.items()))
        print("[reset] 분류 체계(diseases/findings/rois)는 보존했습니다.")

    n_total = 0
    n_ok = 0
    n_replaced = 0
    n_skipped_lateral = 0
    n_skipped_view = 0
    n_missing_file = 0
    n_skipped_disease_cap = 0
    per_disease: Counter[str] = Counter()
    started = time.time()
    capped: defaultdict[str, int] = defaultdict(int)

    for row in iter_rows(csv_file):
        if args.limit and n_total >= args.limit:
            break

        if args.frontal_only and row.get("Frontal/Lateral", "") != "Frontal":
            n_skipped_lateral += 1
            continue
        if args.view and row.get("AP/PA", "") != args.view:
            n_skipped_view += 1
            continue

        tags = row_to_disease_tags(row, args.uncertainty)
        if not tags and args.skip_no_finding:
            continue

        # 균형 표본
        if args.max_per_disease > 0 and tags:
            if any(capped[t] >= args.max_per_disease for t in tags):
                n_skipped_disease_cap += 1
                continue

        img_path = resolve_image_path(archive, row["Path"])
        if not img_path.exists():
            n_missing_file += 1
            continue

        try:
            with open(img_path, "rb") as f:
                image_bytes = f.read()
            view = row.get("AP/PA", "") or ("Lateral" if row.get("Frontal/Lateral") == "Lateral" else "PA")
            patient_age = row.get("Age", "")
            sex = row.get("Sex", "") or None
            metadata = CaseRegisterMetadata(
                view=view if view else "PA",
                patientAge=int(patient_age) if patient_age.isdigit() else None,
                sex=sex,
                source="chexpert_v1.0_small",
            )
            # 키를 CSV 의 Path 에서 유도한다. 같은 원본은 같은 케이스가 되어
            # 재실행이 덮어쓰기가 되고, 중간에 죽은 실행도 이어서 돌릴 수 있다.
            # 무작위 키를 쓰던 동안에는 실행마다 코퍼스가 통째로 복제됐는데,
            # 각 실행이 이미지를 새 경로에 복사하므로 imagePath 로 묶어 세도
            # 드러나지 않았다.
            res = case_service.register_case(
                image_bytes=image_bytes,
                original_filename=img_path.name,
                disease_tags=tags,
                finding_tags=None,
                metadata=metadata,
                case_key=case_key_for_source(row["Path"]),
            )
            n_ok += 1
            if res.get("status") == "replaced":
                n_replaced += 1
            for t in tags:
                capped[t] += 1
                per_disease[t] += 1
            if not tags:
                per_disease["__no_finding__"] += 1
        except Exception as e:
            print(f"[err] {img_path.name}: {e}")
        finally:
            n_total += 1

        if n_total % args.batch == 0:
            elapsed = time.time() - started
            rate = n_total / max(elapsed, 1e-3)
            print(f"[progress] processed={n_total} ok={n_ok} "
                  f"missing={n_missing_file} lateral_skipped={n_skipped_lateral} "
                  f"view_skipped={n_skipped_view} cap_skipped={n_skipped_disease_cap}  {rate:.2f} rows/s")

    elapsed = time.time() - started
    print()
    print("============================== SUMMARY ==============================")
    print(f"processed     : {n_total}")
    print(f"registered    : {n_ok} (신규 {n_ok - n_replaced}, 덮어씀 {n_replaced})")
    print(f"missing files : {n_missing_file}")
    print(f"lateral skip  : {n_skipped_lateral}")
    print(f"view skip     : {n_skipped_view}")
    print(f"cap skip      : {n_skipped_disease_cap}")
    print(f"elapsed       : {elapsed:.1f}s ({n_total/max(elapsed,1e-3):.2f} rows/s)")
    # 어떤 ROI 분할기로 시드했는지, 그리고 몇 건이 fallback 했는지를 요약에 남긴다.
    # 로그를 스크롤해서 세는 것 말고는 알 방법이 없었다 - 케이스 문서의
    # roiMaskVersion 은 어댑터 단위 값이라 케이스별 fallback 을 구분하지 못한다.
    roi_model = getattr(container.roi, "model", None)
    print(f"roi adapter   : {container.roi_status} ({container.roi_mask_version})")
    fb = getattr(roi_model, "fallback_count", None)
    if fb is not None:
        print(f"roi fallbacks : {fb} / {n_ok} 건 (fallback 은 WARNING 으로도 남는다)")

    print("disease distribution (registered):")
    for k, v in per_disease.most_common():
        print(f"  {k:35s} {v}")

    # 이 실행이 끝난 뒤 코퍼스가 실제로 어떤 상태인지 남긴다.
    #
    # 이 스크립트가 방금 무엇을 했는지만 세면, 이전 실행이 남긴 것과 섞여
    # 있어도 요약은 정상으로 보인다. 실제로 202장짜리 split 을 세 번 돌려
    # 573건이 쌓이고 마스크 기준이 두 종류로 갈린 적이 있는데, 그때 요약은
    # 매번 "registered 202" 였다. 코퍼스를 직접 세어야 그것이 드러난다.
    _print_corpus_state(container)
    print("====================================================================")
    return 0


def _print_corpus_state(container) -> None:
    """적재 후 코퍼스의 건수와 출처 분포를 출력한다.

    roiMaskVersion 이나 embeddingVersion 이 두 종류 이상이면 서로 다른 기준으로
    만들어진 벡터가 한 코퍼스에 섞여 있다는 뜻이다. 그 상태에서는 유사도 검색이
    다른 해부 기준끼리를 비교하므로, 전량 재적재(--reset) 전까지 결과를 믿을 수
    없다. 조회가 실패해도 적재 자체는 끝난 뒤이므로 경고만 남기고 넘어간다.
    """
    try:
        rows = list(container.repo.db.aql.execute(
            "FOR c IN xray_cases "
            "COLLECT roi = c.roiMaskVersion, emb = c.embeddingVersion WITH COUNT INTO n "
            "SORT n DESC RETURN [roi, emb, n]"
        ))
    except Exception as e:  # 적재는 끝났다. 요약을 못 냈다고 실패로 만들지 않는다.
        print(f"corpus state  : 조회 실패({e}) - ArangoDB 에서 직접 확인하세요")
        return

    total = sum(n for _, _, n in rows)
    print(f"corpus total  : {total}건")
    for roi, emb, n in rows:
        print(f"  roiMask={roi}  embedding={emb}  {n}건")
    if len(rows) > 1:
        print("  [warn] 출처가 여러 종류다. 서로 다른 기준으로 만든 벡터가 섞여 있어")
        print("         유사도 검색이 다른 해부 기준끼리를 비교한다.")
        print("         --reset 을 붙여 전량 재적재해야 한다.")


if __name__ == "__main__":
    raise SystemExit(main())
