import torch
import torch.nn.functional as F
import torch.nn as nn
from torchvision import transforms, utils
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import numpy as np
import os
from matplotlib import pyplot as plt
import random
import copy
import pandas as pd
from pathlib import Path
import cv2
import time
import multiprocessing
import tempfile


def is_main_process():
    """메인 프로세스인지 확인 (워커 프로세스에서 로그 중복 방지)"""
    try:
        return multiprocessing.current_process().name == 'MainProcess'
    except:
        return True  # multiprocessing이 없거나 확인 불가 시 True 반환


def safe_print(*args, **kwargs):
    """메인 프로세스에서만 출력 (워커 프로세스에서는 로그 중복 방지)"""
    if is_main_process():
        print(*args, **kwargs)
    
    def __len__(self):
        return len(self.cache)

# HybridGNetSegmenter import (옵션 - 마스킹 사용 시)
# utils/segmentation_processing 모듈 사용
try:
    import sys
    # anomaly_squid 디렉토리를 sys.path에 추가
    # anomaly_squid/dataloader/dataloader_chexpert.py -> parents[0]=dataloader, parents[1]=anomaly_squid
    anomaly_squid_path = Path(__file__).resolve().parents[1]
    if str(anomaly_squid_path) not in sys.path:
        sys.path.insert(0, str(anomaly_squid_path))
    from utils.segmentation_processing.hybridgnet_segmenter import HybridGNetSegmenter
    HYBRIDGNET_AVAILABLE = True
except (ImportError, FileNotFoundError, Exception) as e:
    HYBRIDGNET_AVAILABLE = False
    print(f"Warning: HybridGNetSegmenter not available. Masking will be disabled.")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    import traceback
    traceback.print_exc()

class CheXpert(torch.utils.data.Dataset):
    def __init__(self, root, train=True, img_size=(256, 256), normalize=False, enable_transform=True, data_type='pa', full=True, enable_masking=False, device=None, zhanglab_root=None):
        """
        Args:
            root: archive 폴더 경로 (CSV와 이미지가 있는 루트)
            train: 학습용 여부
            img_size: 이미지 크기
            normalize: 정규화 여부
            enable_transform: 데이터 증강 여부
            data_type: 데이터 타입 ('pa' 등, 사용하지 않지만 호환성 유지)
            full: 전체 데이터 사용 여부
            enable_masking: 마스킹 기능 활성화 여부
            device: 마스크 생성에 사용할 디바이스 (None이면 자동)
            zhanglab_root: zhanglab 데이터 폴더 경로 (None이면 사용하지 않음)
        """
        self.data = []
        self.train = train
        self.root = Path(root)
        self.zhanglab_root = Path(zhanglab_root) if zhanglab_root else None
        self.normalize = normalize
        self.img_size = img_size
        self.mean = 0.1307
        self.std = 0.3081
        self.full = full
        self.data_type = data_type
        self.enable_masking = enable_masking and HYBRIDGNET_AVAILABLE
        
        # 마스킹 관련 설정
        self.segmenter = None
        self.mask_cache = {}  # 마스크 캐싱 (성능 향상, 메모리 캐시)
        self.mask_generation_started = False  # 마스크 생성 시작 여부
        self.mask_generation_count = 0  # 생성된 마스크 개수
        self.mask_start_time = None  # 마스크 생성 시작 시간
        self._disk_load_count = 0  # 디스크에서 로드한 마스크 개수
        self._disk_load_started = False  # 디스크 로드 시작 여부
        
        # 마스크 디스크 저장 경로 설정: root 디렉토리 옆에 {root}_masks 디렉토리 생성
        if self.enable_masking:
            # root가 archive_pa라면 archive_pa_masks 디렉토리 생성
            root_parent = self.root.parent
            root_name = self.root.name
            self.mask_root = root_parent / f"{root_name}_masks"
            self.mask_root.mkdir(parents=True, exist_ok=True)
            # 디버그 출력 제거
            # print(f"마스크 저장 경로: {self.mask_root}")
        
        if self.enable_masking:
            try:
                self.segmenter = HybridGNetSegmenter(device=device)
                print("마스킹 기능 활성화: HybridGNetSegmenter 초기화 완료")
            except Exception as e:
                print(f"Warning: 마스킹 기능 초기화 실패. 마스킹 비활성화. Error: {e}")
                self.enable_masking = False

        print('Loading type:', data_type)

        if train:
            if enable_transform:
                self.transforms = transforms.Compose([
                    transforms.RandomAffine(0, translate=(0.05, 0.05), scale=(0.95, 1.05)),
                    transforms.ToTensor()
                ])
                # 마스킹 사용 시 이미지와 동일한 변환을 적용하기 위해 별도 처리
                self.mask_transforms = transforms.Compose([
                    transforms.RandomAffine(0, translate=(0.05, 0.05), scale=(0.95, 1.05)),
                    transforms.ToTensor()
                ])
            else:
                self.transforms = transforms.ToTensor()
                self.mask_transforms = transforms.ToTensor()
        else:
            self.transforms = transforms.ToTensor()
            self.mask_transforms = transforms.ToTensor()

        self.load_data()

    def load_data(self):
        """archive 폴더 구조에 맞게 데이터 로드"""
        if self.train:
            # 학습 데이터: train.csv에서 정상 데이터만 로드
            csv_path = self.root / 'train.csv'
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                print(f"train.csv 로드: {len(df)}개 행")
                
                # archive_pa에는 이미 PA 데이터만 있으므로 필터링 불필요
                # archive를 사용하는 경우에만 PA 필터링 (현재는 사용하지 않음)
                # 정상 데이터만 사용 (No Finding == 1.0)
                if 'No Finding' in df.columns:
                    df = df[df['No Finding'] == 1.0]
                    print(f"정상 데이터 필터링: {len(df)}개")
                
                for idx, row in df.iterrows():
                    path_str = str(row['Path'])
                    
                    # 경로 수정 (archive 구조에 맞게)
                    if path_str.startswith('CheXpert-v1.0-small/train/'):
                        path_str = path_str.replace('CheXpert-v1.0-small/train/', 'train/')
                    elif not path_str.startswith('train/'):
                        path_str = f"train/{path_str}"
                    
                    img_path = self.root / path_str
                    
                    if not img_path.exists():
                        # 다른 경로 시도
                        alt_path = self.root / path_str.split('/', 1)[-1] if '/' in path_str else self.root / path_str
                        if alt_path.exists():
                            img_path = alt_path
                        else:
                            continue
                    
                    self.data.append((str(img_path), 0))  # 정상 데이터는 라벨 0
            else:
                # CSV가 없으면 train 폴더에서 직접 로드
                train_dir = self.root / 'train'
                if train_dir.exists():
                    for img_file in train_dir.rglob('*.jpg'):
                        self.data.append((str(img_file), 0))
                    for img_file in train_dir.rglob('*.png'):
                        self.data.append((str(img_file), 0))
            
            # ===== zhanglab 데이터 추가 (train용 정상 데이터) =====
            if self.zhanglab_root:
                zhanglab_train_dir = self.zhanglab_root / 'train' / 'normal_256'
                if zhanglab_train_dir.exists():
                    zhanglab_count = 0
                    for img_file in zhanglab_train_dir.rglob('*.jpg'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_count += 1
                    for img_file in zhanglab_train_dir.rglob('*.png'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_count += 1
                    for img_file in zhanglab_train_dir.rglob('*.jpeg'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_count += 1
                    if zhanglab_count > 0:
                        print(f'zhanglab train 데이터 추가: {zhanglab_count}개')
        else:
            # 검증/테스트 데이터: valid.csv 또는 test.csv 사용
            csv_path = self.root / 'valid.csv'
            if not csv_path.exists():
                csv_path = self.root / 'test.csv'
            
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                print(f"{csv_path.name} 로드: {len(df)}개 행")
                
                for idx, row in df.iterrows():
                    path_str = str(row['Path'])
                    
                    # 경로 수정
                    if path_str.startswith('CheXpert-v1.0-small/valid/'):
                        path_str = path_str.replace('CheXpert-v1.0-small/valid/', 'valid/')
                    elif path_str.startswith('CheXpert-v1.0-small/train/'):
                        path_str = path_str.replace('CheXpert-v1.0-small/train/', 'train/')
                    elif not (path_str.startswith('valid/') or path_str.startswith('train/')):
                        path_str = f"valid/{path_str}"
                    
                    img_path = self.root / path_str
                    
                    if not img_path.exists():
                        alt_path = self.root / path_str.split('/', 1)[-1] if '/' in path_str else self.root / path_str
                        if alt_path.exists():
                            img_path = alt_path
                        else:
                            continue
                    
                    # 라벨 결정
                    if 'No Finding' in df.columns:
                        label = 0 if row.get('No Finding', 0) == 1.0 else 1
                    else:
                        label = 0  # 기본값: 정상
                    
                    if not self.full and len(self.data) >= 10:
                        break
                    
                    self.data.append((str(img_path), label))
            else:
                # CSV가 없으면 valid/test 폴더에서 직접 로드
                valid_dir = self.root / 'valid'
                test_dir = self.root / 'test'
                
                for img_file in valid_dir.rglob('*.jpg') if valid_dir.exists() else []:
                    self.data.append((str(img_file), 0))
                for img_file in valid_dir.rglob('*.png') if valid_dir.exists() else []:
                    self.data.append((str(img_file), 0))
                for img_file in test_dir.rglob('*.jpg') if test_dir.exists() else []:
                    self.data.append((str(img_file), 0))
                for img_file in test_dir.rglob('*.png') if test_dir.exists() else []:
                    self.data.append((str(img_file), 0))
            
            # ===== zhanglab 데이터 추가 (validation용 정상/비정상 데이터) =====
            if self.zhanglab_root:
                zhanglab_val_normal_dir = self.zhanglab_root / 'val' / 'normal_256'
                zhanglab_val_pneumonia_dir = self.zhanglab_root / 'val' / 'pneumonia_256'
                
                zhanglab_normal_count = 0
                if zhanglab_val_normal_dir.exists():
                    for img_file in zhanglab_val_normal_dir.rglob('*.jpg'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_normal_count += 1
                    for img_file in zhanglab_val_normal_dir.rglob('*.png'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_normal_count += 1
                    for img_file in zhanglab_val_normal_dir.rglob('*.jpeg'):
                        self.data.append((str(img_file), 0))  # 정상 데이터는 라벨 0
                        zhanglab_normal_count += 1
                
                zhanglab_pneumonia_count = 0
                if zhanglab_val_pneumonia_dir.exists():
                    for img_file in zhanglab_val_pneumonia_dir.rglob('*.jpg'):
                        self.data.append((str(img_file), 1))  # 비정상 데이터는 라벨 1
                        zhanglab_pneumonia_count += 1
                    for img_file in zhanglab_val_pneumonia_dir.rglob('*.png'):
                        self.data.append((str(img_file), 1))  # 비정상 데이터는 라벨 1
                        zhanglab_pneumonia_count += 1
                    for img_file in zhanglab_val_pneumonia_dir.rglob('*.jpeg'):
                        self.data.append((str(img_file), 1))  # 비정상 데이터는 라벨 1
                        zhanglab_pneumonia_count += 1
                
                if zhanglab_normal_count > 0 or zhanglab_pneumonia_count > 0:
                    print(f'zhanglab validation 데이터 추가: 정상 {zhanglab_normal_count}개, 비정상 {zhanglab_pneumonia_count}개')
        
        print('%d data loaded from: %s' % (len(self.data), self.root))
        
        # 마스킹 활성화 시 디스크에 저장된 마스크 통계 출력 및 검증
        if self.enable_masking:
            self._check_disk_mask_statistics()
            # 데이터와 마스크 일치 여부 검증
            self._validate_mask_data_matching()
    
    def _check_disk_mask_statistics(self):
        """디스크에 저장된 마스크 통계 확인"""
        if not hasattr(self, 'mask_root') or not self.mask_root.exists():
            return
        
        saved_count = 0
        for img_path, _ in self.data:
            mask_path = self._get_mask_path(Path(img_path))
            if mask_path.exists():
                saved_count += 1
        
        # 디버그 출력 제거: 마스크 디스크 캐시 통계는 조용히 처리
        # total_count = len(self.data)
        # if saved_count > 0:
        #     saved_pct = (saved_count / total_count) * 100
        #     print(f"[마스크 디스크 캐시] {saved_count}/{total_count}개 마스크 파일이 디스크에 저장되어 있음 ({saved_pct:.1f}%)")
        #     print(f"[마스크 저장 경로] {self.mask_root}")
        #     if saved_count < total_count:
        #         missing_count = total_count - saved_count
        #         print(f"[마스크 생성 필요] {missing_count}개 마스크를 생성해야 함")
        # else:
        #     print(f"[마스크 디스크 캐시] 디스크에 저장된 마스크 파일 없음 (모든 마스크를 생성해야 함)")
    
    def _validate_mask_data_matching(self):
        """데이터와 마스크가 올바르게 매칭되는지 검증"""
        archive_pa_data = []
        zhanglab_data = []
        
        # 데이터 분류
        for img_path, label in self.data:
            img_path = Path(img_path)
            if self.zhanglab_root and img_path.is_relative_to(self.zhanglab_root):
                zhanglab_data.append((img_path, label))
            else:
                archive_pa_data.append((img_path, label))
        
        # archive_pa 데이터와 마스크 검증
        archive_pa_missing = []
        archive_pa_mismatch = []
        for img_path, label in archive_pa_data:
            if not img_path.exists():
                archive_pa_mismatch.append((str(img_path), "이미지 파일 없음"))
                continue
            mask_path = self._get_mask_path(img_path)
            if not mask_path.exists():
                archive_pa_missing.append(str(img_path))
        
        # zhanglab 데이터와 마스크 검증
        zhanglab_missing = []
        zhanglab_mismatch = []
        for img_path, label in zhanglab_data:
            if not img_path.exists():
                zhanglab_mismatch.append((str(img_path), "이미지 파일 없음"))
                continue
            mask_path = self._get_mask_path(img_path)
            if not mask_path.exists():
                zhanglab_missing.append(str(img_path))
        
        # 검증 결과 출력 제거: 마스크-데이터 매칭 검증은 조용히 수행
        # print("=" * 80)
        # print("[마스크-데이터 매칭 검증]")
        # print("=" * 80)
        # print(f"archive_pa 데이터: {len(archive_pa_data)}개")
        # print(f"  - 마스크 존재: {len(archive_pa_data) - len(archive_pa_missing)}개")
        # print(f"  - 마스크 없음: {len(archive_pa_missing)}개")
        # if archive_pa_missing:
        #     print(f"  - 마스크 없는 파일 (처음 5개):")
        #     for path in archive_pa_missing[:5]:
        #         print(f"    {path}")
        # 
        # print(f"\nzhanglab 데이터: {len(zhanglab_data)}개")
        # print(f"  - 마스크 존재: {len(zhanglab_data) - len(zhanglab_missing)}개")
        # print(f"  - 마스크 없음: {len(zhanglab_missing)}개")
        # if zhanglab_missing:
        #     print(f"  - 마스크 없는 파일 (처음 5개):")
        #     for path in zhanglab_missing[:5]:
        #         print(f"    {path}")
        # 
        # # 마스크 경로 확인
        # if archive_pa_data:
        #     sample_img = archive_pa_data[0][0]
        #     sample_mask = self._get_mask_path(sample_img)
        #     print(f"\narchive_pa 마스크 경로 예시:")
        #     print(f"  이미지: {sample_img}")
        #     print(f"  마스크: {sample_mask}")
        #     print(f"  마스크 존재: {sample_mask.exists()}")
        # 
        # if zhanglab_data:
        #     sample_img = zhanglab_data[0][0]
        #     sample_mask = self._get_mask_path(sample_img)
        #     print(f"\nzhanglab 마스크 경로 예시:")
        #     print(f"  이미지: {sample_img}")
        #     print(f"  마스크: {sample_mask}")
        #                 print(f"  마스크 존재: {sample_mask.exists()}")
        
        # print("=" * 80)
    
    def _get_mask_path(self, image_path: Path) -> Path:
        """이미지 경로에서 마스크 저장 경로를 계산"""
        image_path = Path(image_path)
        
        # zhanglab 데이터인지 확인 (is_relative_to 사용으로 더 안전하게)
        if self.zhanglab_root:
            try:
                if image_path.is_relative_to(self.zhanglab_root):
                    # zhanglab 데이터는 zhanglab_root 기준으로 상대 경로 계산
                    relative_path = image_path.relative_to(self.zhanglab_root)
                    # zhanglab 마스크는 별도 디렉토리에 저장
                    zhanglab_mask_root = self.mask_root.parent / f"{self.mask_root.name}_zhanglab"
                    zhanglab_mask_root.mkdir(parents=True, exist_ok=True)
                    mask_file_path = zhanglab_mask_root / relative_path.with_suffix('.mask.npy')
                    return mask_file_path
            except ValueError:
                # is_relative_to가 실패하면 (절대 경로 문제 등) startswith로 폴백
                if str(image_path).startswith(str(self.zhanglab_root)):
                    relative_path = image_path.relative_to(self.zhanglab_root)
                    zhanglab_mask_root = self.mask_root.parent / f"{self.mask_root.name}_zhanglab"
                    zhanglab_mask_root.mkdir(parents=True, exist_ok=True)
                    mask_file_path = zhanglab_mask_root / relative_path.with_suffix('.mask.npy')
                    return mask_file_path
        
        # archive_pa 데이터 또는 zhanglab이 아닌 경우
        # 원본 데이터는 root 기준으로 상대 경로 계산
        try:
            relative_path = image_path.relative_to(self.root)
        except ValueError:
            # 상대 경로 계산 실패 시 (절대 경로 문제 등)
            # 이미지 파일명만 사용
            relative_path = Path(image_path.name)
        
        mask_file_path = self.mask_root / relative_path.with_suffix('.mask.npy')
        return mask_file_path
    
    def _load_mask_from_disk(self, mask_path: Path) -> np.ndarray:
        """디스크에서 마스크 로드"""
        if mask_path.exists():
            try:
                mask = np.load(str(mask_path))
                # img_size와 일치하는지 확인
                if mask.shape == self.img_size:
                    return mask
                else:
                    # 크기가 다르면 리사이즈 (예: img_size가 변경된 경우)
                    mask_resized = cv2.resize(mask, self.img_size, interpolation=cv2.INTER_NEAREST)
                    # 리사이즈된 마스크 저장
                    np.save(str(mask_path), mask_resized)
                    return mask_resized
            except Exception as e:
                safe_print(f"Warning: 마스크 파일 로드 실패 ({mask_path}): {e}")
                return None
        return None
    
    def _save_mask_to_disk(self, mask: np.ndarray, mask_path: Path):
        """마스크를 디스크에 저장"""
        try:
            # 디렉토리 생성
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            # 마스크 저장
            np.save(str(mask_path), mask)
        except Exception as e:
            safe_print(f"Warning: 마스크 파일 저장 실패 ({mask_path}): {e}")
    
    def _generate_mask(self, image_path: Path) -> np.ndarray:
        """마스크 생성 (메모리 캐싱 및 디스크 캐싱 지원)"""
        image_path = Path(image_path)
        
        # 1. 메모리 캐시 확인
        if str(image_path) in self.mask_cache:
            return self.mask_cache[str(image_path)]
        
        if not self.enable_masking or self.segmenter is None:
            # 마스킹 비활성화 시 전체 영역 마스크 반환 (모든 픽셀 1)
            mask = np.ones(self.img_size, dtype=np.uint8)
            self.mask_cache[str(image_path)] = mask
            return mask
        
        # 2. 디스크에서 마스크 로드 시도
        mask_path = self._get_mask_path(image_path)
        mask = self._load_mask_from_disk(mask_path)
        
        if mask is not None:
            # 디스크에서 로드 성공
            self.mask_cache[str(image_path)] = mask  # 메모리 캐시에도 저장
            
            # 디스크 로드 카운트만 증가 (로그 출력 제거)
            if not self._disk_load_started:
                self._disk_load_started = True
            self._disk_load_count += 1
            
            return mask
        
        # 3. 마스크가 없으면 생성
        # 마스크 생성 시작 시간 기록 (로그 출력 제거)
        if not self.mask_generation_started:
            self.mask_generation_started = True
            self.mask_start_time = time.time()
        
        try:
            # ===== 중요: 모델 입력 크기(256x256)로 리사이즈된 이미지로 마스크 생성 =====
            # 1. 이미지를 먼저 모델 입력 크기(256x256)로 리사이즈
            original_image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
            if original_image is None:
                raise FileNotFoundError(f"Unable to read image: {image_path}")
            
            # 모델 입력 크기로 리사이즈 (이미지와 동일한 방식으로)
            resized_image = cv2.resize(original_image, self.img_size, interpolation=cv2.INTER_LINEAR)
            
            # 2. 리사이즈된 이미지를 임시 파일로 저장하여 HybridGNetSegmenter에 전달
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                cv2.imwrite(str(tmp_path), resized_image)
            
            try:
                # 3. 리사이즈된 이미지로 마스크 생성 (이미 256x256 크기)
                mask = self.segmenter.generate_mask(tmp_path)
                
                # 4. 마스크가 이미 256x256 크기인지 확인하고, 필요시 리사이즈
                if mask.shape != self.img_size:
                    # 크기가 다르면 리사이즈 (INTER_NEAREST 사용하여 이진 마스크 유지)
                    mask = cv2.resize(mask, self.img_size, interpolation=cv2.INTER_NEAREST)
            finally:
                # 임시 파일 삭제
                if tmp_path.exists():
                    tmp_path.unlink()
            
            # 마스크 검증: 마스크가 모두 1이면 문제가 있음
            if mask.min() == mask.max() == 1:
                safe_print(f"Warning: 마스크가 모두 1로 생성됨 ({image_path}). 마스크 생성 실패로 간주하고 전체 영역 마스크 사용.")
                mask = np.ones(self.img_size, dtype=np.uint8)
                self.mask_cache[str(image_path)] = mask
                self._save_mask_to_disk(mask, mask_path)
                return mask
            
            # 마스크가 이미 256x256 크기이므로 추가 리사이즈 불필요
            # 하지만 shape 확인
            if mask.shape != self.img_size:
                safe_print(f"Warning: 마스크 크기가 예상과 다름. {mask.shape} -> {self.img_size}로 리사이즈")
                mask = cv2.resize(mask, self.img_size, interpolation=cv2.INTER_NEAREST)
            
            # 5. 디스크에 마스크 저장 (256x256 크기)
            self._save_mask_to_disk(mask, mask_path)
            
            # 6. 메모리 캐시에 저장
            self.mask_cache[str(image_path)] = mask
            self.mask_generation_count += 1
            
            return mask
        except Exception as e:
            safe_print(f"Warning: 마스크 생성 실패 ({image_path}): {e}. 전체 영역 마스크 사용.")
            mask = np.ones(self.img_size, dtype=np.uint8)
            self.mask_cache[str(image_path)] = mask
            # 실패한 경우에도 디스크에 저장 (다음에는 전체 영역 마스크를 바로 로드)
            self._save_mask_to_disk(mask, mask_path)
            return mask

    def __getitem__(self, index):
        img_path, label = copy.deepcopy(self.data[index])
        img_path = Path(img_path)
        
        # 이미지 로드
        img = Image.open(img_path).convert('L').resize(self.img_size)  # Grayscale
        
        # 마스크 생성 (마스킹 활성화 시)
        if self.enable_masking:
            mask_np = self._generate_mask(img_path)
            # PIL Image로 변환
            mask_pil = Image.fromarray(mask_np * 255).convert('L')
            
            # 이미지와 마스크에 동일한 변환 적용 (학습 시 데이터 증강)
            if self.train and hasattr(self, 'mask_transforms'):
                # 변환을 위해 이미지와 마스크를 함께 처리
                seed = np.random.randint(2147483647)
                random.seed(seed)
                torch.manual_seed(seed)
                img = self.transforms(img)
                random.seed(seed)
                torch.manual_seed(seed)
                mask = self.mask_transforms(mask_pil)
            else:
                img = self.transforms(img)
                mask = self.mask_transforms(mask_pil)
            
            # 마스크를 0/1로 정규화
            mask = (mask > 0.5).float()
        else:
            img = self.transforms(img)
            # 마스킹 비활성화 시 전체 영역 마스크 (모든 픽셀 1)
            mask = torch.ones_like(img)
        
        if self.normalize:
            img -= self.mean
            img /= self.std
        
        # 이미지, 마스크, 라벨 반환
        return img, mask, (torch.zeros((1,)) + label).long()

    def __len__(self):
        return len(self.data)

if __name__ == '__main__':
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent.parent.parent
    archive_root = project_root / 'mvtec_root' / 'chest_xray' / 'archive_pa'
    
    dataset = CheXpert(str(archive_root), train=True, img_size=(128, 128), data_type='pa', enable_masking=False)
    trainloader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=True, num_workers=0)
    for i, (img, mask, label) in enumerate(trainloader):
        print(img.shape, mask.shape, label.shape, torch.max(img))
        if i >= 2:
            break
