"""
archive에서 필터링 조건을 만족하는 데이터만 선택하여 archive_pa 폴더를 생성하는 스크립트

필터링 조건:
1. AP/PA가 "AP"가 아닌 값 (PA, null, 빈 값 모두 포함)
2. Support Devices가 0.0
3. Frontal/Lateral이 "Frontal"인 값
"""
import pandas as pd
import shutil
from pathlib import Path
import argparse
from tqdm import tqdm


def is_pa_frontal(row):
    """필터링 조건을 만족하는 이미지인지 확인
    1. AP/PA가 "AP"가 아닌 값 (null 포함)
    2. Support Devices가 0.0
    3. Frontal/Lateral이 "Frontal"인 값
    """
    # 조건 1: AP/PA가 "AP"가 아니어야 함 (PA이거나 null/빈 값이면 OK)
    ap_pa_value = row.get("AP/PA", "")
    
    # null/빈 값 체크
    if pd.isna(ap_pa_value) or str(ap_pa_value).strip() == "":
        is_not_ap = True  # null/빈 값은 AP가 아니므로 포함
    else:
        # "AP"가 아니면 포함
        view = str(ap_pa_value).strip().upper()
        is_not_ap = (view != "AP")
    
    # 조건 2: Support Devices가 0.0이어야 함
    support_devices = row.get("Support Devices", "")
    is_support_devices_zero = False
    
    # Support Devices 값 확인
    if pd.isna(support_devices) or str(support_devices).strip() == "":
        # null/빈 값은 0.0으로 간주
        is_support_devices_zero = True
    else:
        try:
            support_devices_value = float(support_devices)
            is_support_devices_zero = (support_devices_value == 0.0)
        except (ValueError, TypeError):
            # 변환할 수 없는 값은 0.0으로 간주하지 않음
            is_support_devices_zero = False
    
    # 조건 3: Frontal/Lateral이 "Frontal"이어야 함
    frontal_lateral_value = row.get("Frontal/Lateral", "")
    is_frontal = False
    
    # Frontal/Lateral 값 확인
    if pd.isna(frontal_lateral_value) or str(frontal_lateral_value).strip() == "":
        # null/빈 값은 Frontal로 간주하지 않음
        is_frontal = False
    else:
        plane = str(frontal_lateral_value).strip().upper()
        is_frontal = (plane == "FRONTAL")
    
    return is_not_ap and is_support_devices_zero and is_frontal


def copy_image(source_path, target_path, source_root, target_root):
    """이미지 파일을 복사"""
    source_file = source_root / source_path
    target_file = target_root / target_path
    
    # 타겟 디렉토리 생성
    target_file.parent.mkdir(parents=True, exist_ok=True)
    
    if source_file.exists():
        shutil.copy2(source_file, target_file)
        return True
    else:
        # 경로 수정 시도
        alt_path = source_root / source_path.split('/', 1)[-1] if '/' in str(source_path) else source_root / source_path
        if alt_path.exists():
            shutil.copy2(alt_path, target_file)
            return True
        return False


def process_split(split, source_root, target_root, limit=None):
    """train 또는 valid split 처리"""
    print(f"\n[{split.upper()}] 처리 시작...")
    
    # CSV 파일 경로
    source_csv = source_root / f"{split}.csv"
    target_csv = target_root / f"{split}.csv"
    
    if not source_csv.exists():
        print(f"경고: {source_csv} 파일이 없습니다. 건너뜁니다.")
        return
    
    # CSV 읽기
    print(f"CSV 파일 로드 중: {source_csv}")
    df = pd.read_csv(source_csv)
    print(f"전체 데이터: {len(df)}개")
    
    # 필터링 적용: AP가 아니고(null 포함), Support Devices가 0.0, Frontal 이미지
    filter_mask = df.apply(is_pa_frontal, axis=1)
    df_filtered = df[filter_mask].copy()
    print(f"필터링된 데이터: {len(df_filtered)}개 (AP가 아니고, Support Devices=0.0, Frontal)")
    
    if len(df_filtered) == 0:
        print(f"경고: {split}에 필터링 조건을 만족하는 데이터가 없습니다.")
        return
    
    # limit이 있으면 제한
    if limit:
        df_filtered = df_filtered.head(limit)
        print(f"제한 적용: {len(df_filtered)}개로 제한")
    
    # 타겟 디렉토리 생성
    target_root.mkdir(parents=True, exist_ok=True)
    
    # 이미지 복사 및 경로 수정
    copied_count = 0
    failed_paths = []
    
    print("이미지 복사 중...")
    for idx, row in tqdm(df_filtered.iterrows(), total=len(df_filtered), desc=f"Copying {split}"):
        path_str = str(row['Path'])
        
        # 경로 정규화
        if path_str.startswith('CheXpert-v1.0-small/'):
            # CheXpert-v1.0-small/train/... -> train/...
            path_str = path_str.replace('CheXpert-v1.0-small/', '')
        elif not (path_str.startswith('train/') or path_str.startswith('valid/')):
            # 상대 경로가 없으면 split 폴더 추가
            path_str = f"{split}/{path_str}"
        
        # 이미지 복사
        if copy_image(path_str, path_str, source_root, target_root):
            # CSV의 Path 컬럼 업데이트
            df_filtered.at[idx, 'Path'] = path_str
            copied_count += 1
        else:
            failed_paths.append(path_str)
    
    # 실패한 경로 출력
    if failed_paths:
        print(f"\n경고: {len(failed_paths)}개 이미지를 찾을 수 없습니다:")
        for path in failed_paths[:10]:  # 처음 10개만 출력
            print(f"  - {path}")
        if len(failed_paths) > 10:
            print(f"  ... 외 {len(failed_paths) - 10}개")
    
    # 성공적으로 복사된 데이터만 CSV 저장
    df_filtered_success = df_filtered[df_filtered['Path'].isin([p for p in df_filtered['Path'] if (target_root / p).exists()])]
    
    # CSV 저장
    df_filtered_success.to_csv(target_csv, index=False)
    print(f"\n[{split.upper()}] 완료:")
    print(f"  - 복사된 이미지: {copied_count}개")
    print(f"  - CSV 저장: {target_csv}")
    print(f"  - CSV 행 수: {len(df_filtered_success)}개")


def main():
    parser = argparse.ArgumentParser(description="AP가 아니고 Support Devices=0.0이고 Frontal인 데이터만 필터링해서 archive_pa 폴더 생성")
    parser.add_argument(
        '--source',
        type=str,
        default='mvtec_root/chest_xray/archive',
        help='원본 archive 폴더 경로'
    )
    parser.add_argument(
        '--target',
        type=str,
        default='mvtec_root/chest_xray/archive_pa',
        help='생성할 archive_pa 폴더 경로'
    )
    parser.add_argument(
        '--split',
        type=str,
        choices=['train', 'valid', 'both'],
        default='both',
        help='처리할 split (train, valid, both)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='각 split당 최대 처리 개수 (테스트용)'
    )
    
    args = parser.parse_args()
    
    source_root = Path(args.source)
    target_root = Path(args.target)
    
    if not source_root.exists():
        print(f"에러: 원본 폴더를 찾을 수 없습니다: {source_root}")
        return
    
    print(f"원본 폴더: {source_root}")
    print(f"타겟 폴더: {target_root}")
    print(f"처리할 split: {args.split}")
    
    # split 처리
    if args.split in ['train', 'both']:
        process_split('train', source_root, target_root, args.limit)
    
    if args.split in ['valid', 'both']:
        process_split('valid', source_root, target_root, args.limit)
    
    print("\n모든 작업 완료!")


if __name__ == '__main__':
    main()

