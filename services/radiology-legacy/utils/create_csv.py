"""
archive_pa 폴더의 이미지 파일을 기반으로 CSV 파일 생성
"""

import pandas as pd
from pathlib import Path
import os
from tqdm import tqdm


def create_csv_from_images(archive_root, output_csv=None, split='train', normal_only=True):
    """
    이미지 파일들을 기반으로 CSV 파일 생성
    
    Args:
        archive_root: archive_pa 또는 archive 폴더 경로
        output_csv: 출력 CSV 파일 경로 (None이면 archive_root/{split}.csv)
        split: 'train' 또는 'valid'
        normal_only: True면 모든 데이터를 정상(No Finding=1.0)으로 설정
    """
    archive_root = Path(archive_root)
    
    # 이미지 폴더 경로
    img_dir = archive_root / split
    
    if not img_dir.exists():
        print(f"경고: {img_dir} 폴더가 없습니다.")
        return None
    
    # 이미지 파일 찾기
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = []
    
    print(f"{img_dir}에서 이미지 파일 검색 중...")
    for ext in image_extensions:
        image_files.extend(list(img_dir.rglob(f'*{ext}')))
        image_files.extend(list(img_dir.rglob(f'*{ext.upper()}')))
    
    if len(image_files) == 0:
        print(f"경고: {img_dir}에 이미지 파일이 없습니다.")
        return None
    
    print(f"이미지 파일 {len(image_files)}개 발견")
    
    # CSV 데이터 생성
    data = []
    for img_path in tqdm(image_files, desc="CSV 생성 중"):
        # 상대 경로 계산 (archive_root 기준)
        try:
            relative_path = img_path.relative_to(archive_root)
            # Windows 경로를 Unix 스타일로 변환 (CheXpert 형식)
            path_str = str(relative_path).replace('\\', '/')
        except ValueError:
            # archive_root 밖에 있으면 전체 경로 사용
            path_str = str(img_path)
        
        # CSV 행 생성
        row = {
            'Path': path_str,
            'No Finding': 1.0 if normal_only else 0.0,  # 정상 데이터로 설정
            # 다른 질병 열들은 모두 -1.0 (불확실) 또는 0.0 (없음)으로 설정
            'Enlarged Cardiomediastinum': -1.0,
            'Cardiomegaly': -1.0,
            'Lung Opacity': -1.0,
            'Lung Lesion': -1.0,
            'Edema': -1.0,
            'Consolidation': -1.0,
            'Pneumonia': -1.0,
            'Atelectasis': -1.0,
            'Pneumothorax': -1.0,
            'Pleural Effusion': -1.0,
            'Pleural Other': -1.0,
            'Fracture': -1.0,
            'Support Devices': -1.0,
        }
        data.append(row)
    
    # DataFrame 생성
    df = pd.DataFrame(data)
    
    # 출력 경로 설정
    if output_csv is None:
        output_csv = archive_root / f'{split}.csv'
    else:
        output_csv = Path(output_csv)
    
    # CSV 저장
    df.to_csv(output_csv, index=False)
    print(f"\nCSV 파일 저장: {output_csv}")
    print(f"  - 총 {len(df)}개 행")
    print(f"  - 정상 데이터 (No Finding=1.0): {len(df[df['No Finding'] == 1.0])}개")
    
    return output_csv


def create_csv_from_existing(archive_root, source_csv=None, output_csv=None, split='train'):
    """
    기존 CSV 파일을 기반으로 archive_pa용 CSV 생성
    (경로만 수정)
    
    Args:
        archive_root: archive_pa 폴더 경로
        source_csv: 원본 CSV 파일 경로 (archive/train.csv 등)
        output_csv: 출력 CSV 파일 경로
        split: 'train' 또는 'valid'
    """
    archive_root = Path(archive_root)
    
    # 원본 CSV 파일 찾기
    if source_csv is None:
        # archive 폴더에서 찾기
        archive_path = archive_root.parent / 'archive'
        source_csv = archive_path / f'{split}.csv'
        
        if not source_csv.exists():
            print(f"경고: 원본 CSV 파일을 찾을 수 없습니다: {source_csv}")
            return None
    
    source_csv = Path(source_csv)
    if not source_csv.exists():
        print(f"경고: 원본 CSV 파일이 없습니다: {source_csv}")
        return None
    
    print(f"원본 CSV 읽기: {source_csv}")
    df = pd.read_csv(source_csv)
    print(f"  - 총 {len(df)}개 행")
    
    # Path 열 수정
    print("경로 수정 중...")
    updated_paths = 0
    
    def fix_path(path_str):
        """경로를 archive_pa 기준으로 수정"""
        if pd.isna(path_str):
            return None
        
        path_str = str(path_str)
        # CheXpert-v1.0-small/train/... -> train/... 또는 split/...
        if 'CheXpert-v1.0-small' in path_str:
            path_str = path_str.replace('CheXpert-v1.0-small/', '')
        
        # train/ 또는 valid/로 시작하는지 확인
        if not path_str.startswith(split + '/'):
            # split 폴더 추가
            path_str = f"{split}/{path_str}"
        
        # 실제 파일 존재 확인
        full_path = archive_root / path_str
        if full_path.exists():
            return path_str
        
        # 다른 가능한 경로 시도
        alt_paths = [
            archive_root / split / Path(path_str).name,
            archive_root / path_str.split('/', 1)[-1] if '/' in path_str else path_str,
        ]
        
        for alt_path in alt_paths:
            if alt_path.exists():
                return str(alt_path.relative_to(archive_root)).replace('\\', '/')
        
        return path_str
    
    df['Path'] = df['Path'].apply(fix_path)
    
    # 출력 경로 설정
    if output_csv is None:
        output_csv = archive_root / f'{split}.csv'
    else:
        output_csv = Path(output_csv)
    
    # CSV 저장
    df.to_csv(output_csv, index=False)
    print(f"\nCSV 파일 저장: {output_csv}")
    print(f"  - 총 {len(df)}개 행")
    
    return output_csv


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='archive_pa 폴더용 CSV 파일 생성')
    parser.add_argument('--archive_root', type=str, 
                       default=r'c:\Project\AI\mvtec_root\chest_xray\archive_pa',
                       help='archive_pa 폴더 경로')
    parser.add_argument('--split', type=str, choices=['train', 'valid'], default='train',
                       help='train 또는 valid')
    parser.add_argument('--method', type=str, choices=['images', 'existing'], default='images',
                       help='생성 방법: images (이미지 기반) 또는 existing (기존 CSV 기반)')
    parser.add_argument('--source_csv', type=str, default=None,
                       help='기존 CSV 파일 경로 (method=existing일 때 사용)')
    parser.add_argument('--output_csv', type=str, default=None,
                       help='출력 CSV 파일 경로 (None이면 archive_root/{split}.csv)')
    parser.add_argument('--normal_only', action='store_true', default=True,
                       help='모든 데이터를 정상(No Finding=1.0)으로 설정')
    
    args = parser.parse_args()
    
    archive_root = Path(args.archive_root)
    
    if not archive_root.exists():
        print(f"오류: archive_root 폴더가 없습니다: {archive_root}")
        return
    
    print("="*80)
    print("CSV 파일 생성")
    print("="*80)
    print(f"archive_root: {archive_root}")
    print(f"split: {args.split}")
    print(f"method: {args.method}")
    print("="*80)
    
    if args.method == 'images':
        # 이미지 파일 기반 생성
        create_csv_from_images(
            archive_root=archive_root,
            output_csv=args.output_csv,
            split=args.split,
            normal_only=args.normal_only
        )
    else:
        # 기존 CSV 기반 생성
        create_csv_from_existing(
            archive_root=archive_root,
            source_csv=args.source_csv,
            output_csv=args.output_csv,
            split=args.split
        )
    
    print("\n완료!")


if __name__ == '__main__':
    main()
