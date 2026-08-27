"""
데이터 경로 확인 스크립트
"""

from pathlib import Path
import sys

# 프로젝트 루트 경로
project_root = Path(__file__).parent.parent.parent.parent

# 확인할 경로들
paths_to_check = [
    project_root / 'mvtec_root' / 'chest_xray' / 'archive_pa',
    project_root / 'mvtec_root' / 'chest_xray' / 'archive',
]

print("="*80)
print("데이터 경로 확인")
print("="*80)

found_paths = []

for path in paths_to_check:
    print(f"\n확인 중: {path}")
    if path.exists():
        print(f"  ✓ 폴더 존재")
        
        train_csv = path / 'train.csv'
        valid_csv = path / 'valid.csv'
        
        if train_csv.exists():
            print(f"  ✓ train.csv 존재")
            # CSV 파일 행 수 확인
            try:
                import pandas as pd
                df = pd.read_csv(train_csv)
                print(f"    - 행 수: {len(df):,}개")
            except Exception as e:
                print(f"    - CSV 읽기 실패: {e}")
        else:
            print(f"  ✗ train.csv 없음")
        
        if valid_csv.exists():
            print(f"  ✓ valid.csv 존재")
            try:
                import pandas as pd
                df = pd.read_csv(valid_csv)
                print(f"    - 행 수: {len(df):,}개")
            except Exception as e:
                print(f"    - CSV 읽기 실패: {e}")
        else:
            print(f"  ✗ valid.csv 없음")
        
        # 이미지 폴더 확인
        train_img_dir = path / 'train'
        valid_img_dir = path / 'valid'
        
        if train_img_dir.exists():
            img_count = len(list(train_img_dir.rglob('*.jpg'))) + len(list(train_img_dir.rglob('*.png')))
            print(f"  ✓ train/ 이미지 폴더 존재 (이미지: {img_count}개)")
        else:
            print(f"  ✗ train/ 이미지 폴더 없음")
        
        if valid_img_dir.exists():
            img_count = len(list(valid_img_dir.rglob('*.jpg'))) + len(list(valid_img_dir.rglob('*.png')))
            print(f"  ✓ valid/ 이미지 폴더 존재 (이미지: {img_count}개)")
        else:
            print(f"  ✗ valid/ 이미지 폴더 없음")
        
        found_paths.append(path)
    else:
        print(f"  ✗ 폴더 없음")

print("\n" + "="*80)
if found_paths:
    print(f"사용 가능한 경로: {len(found_paths)}개")
    for p in found_paths:
        print(f"  - {p}")
    print("\nconfig.py가 자동으로 첫 번째 경로를 사용합니다.")
else:
    print("⚠ 경고: 사용 가능한 데이터 경로를 찾을 수 없습니다!")
    print("\n다음 중 하나를 수행하세요:")
    print("1. archive_pa 또는 archive 폴더에 데이터를 준비하세요")
    print("2. roi_mask_pipeline.py를 실행하여 archive_pa를 생성하세요")
    print("3. convert_chexpert_to_mvtec.py를 실행하여 데이터를 준비하세요")
print("="*80)
