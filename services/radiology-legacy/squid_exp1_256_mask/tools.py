import torch
import torch.nn.functional as F
import torch.nn as nn
from PIL import Image
import numpy as np
import os
import matplotlib
# GUI 백엔드 사용 시 macOS에서 크래시가 나므로 headless 모드로 강제
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import random
import multiprocessing
import cv2

import copy
import shutil

import importlib
from tqdm import tqdm
import argparse


def is_main_process():
    """메인 프로세스인지 확인 (워커 프로세스에서 로그 중복 방지)"""
    try:
        return multiprocessing.current_process().name == 'MainProcess'
    except:
        return True  # multiprocessing이 없거나 확인 불가 시 True 반환


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp', type=str, default='squid_exp1')
    parser.add_argument('--config', type=str, default='chexpert_best')
    parser.add_argument('--resume', action='store_true', help='Resume training from checkpoint')
    args, unparsed = parser.parse_known_args()
    return args

def backup_files(args, model_file='squid'):
    # back up files
    shutil.copyfile('configs/'+args.config+'.py', os.path.join('checkpoints', args.exp, 'config.py'))
    shutil.copyfile('models/inpaint.py', os.path.join('checkpoints', args.exp, 'inpaint.py'))
    shutil.copyfile('models/memory.py', os.path.join('checkpoints', args.exp, 'memory.py'))
    shutil.copyfile('models/'+model_file+'.py', os.path.join('checkpoints', args.exp, model_file+'.py'))
    shutil.copyfile('models/discriminator.py', os.path.join('checkpoints', args.exp, 'discriminator.py'))
    shutil.copyfile('models/basic_modules.py', os.path.join('checkpoints', args.exp, 'basic_modules.py'))
    shutil.copyfile('main.py', os.path.join('checkpoints', args.exp, 'main.py'))
    shutil.copyfile('tools.py', os.path.join('checkpoints', args.exp, 'tools.py'))

def build_disc(CONFIG):
    DISC = importlib.import_module('models.discriminator')

    if CONFIG.discriminator_type == 'basic':
        discriminator = DISC.SimpleDiscriminator(size=CONFIG.size).to(CONFIG.device)
        print('Basic discriminator created.')
    elif CONFIG.discriminator_type == 'tiny':
        discriminator = DISC.TinyDiscriminator(size=CONFIG.size).to(CONFIG.device)
        print('Tiny discriminator created.')
    elif CONFIG.discriminator_type == 'big':
        discriminator = DISC.BigDiscriminator(size=CONFIG.size).to(CONFIG.device)
        print('Big discriminator created.')
    elif CONFIG.discriminator_type == 'extratiny':
        discriminator = DISC.ExtraTinyDiscriminator(size=CONFIG.size).to(CONFIG.device)
        print('extratiny discriminator created.')
    return discriminator

def log(log_file, msg):
    """로그 출력 (메인 프로세스에서만 실행)"""
    if not is_main_process():
        return  # 워커 프로세스에서는 로그 출력 안 함
    
    if log_file is not None:
        try:
            log_file.write(msg+'\n')
            log_file.flush()  # 즉시 디스크에 쓰기
        except:
            pass  # 로그 파일 쓰기 실패 시 무시
    
    print(msg)

def log_loss(log_file, epoch, train_loss, val_loss, total_epochs=None):
    """더 직관적인 로그 형식으로 출력"""
    # 진행률 표시 (epoch는 0-based이므로 +1하여 표시)
    if total_epochs:
        progress = f"[{epoch+1}/{total_epochs}]"
        progress_pct = f"({(epoch+1)/total_epochs*100:.1f}%)"
    else:
        progress = f"[{epoch+1}]"
        progress_pct = ""
    
    # 구분선
    separator = "=" * 80
    
    # Epoch 헤더
    header = f"\n{separator}\nEpoch {progress} {progress_pct}\n{separator}"
    print(header)
    log_file.write(header + '\n')
    log_file.flush() 
    
    # Train Loss 섹션
    train_section = "\n[TRAIN]"
    print(train_section)
    log_file.write(train_section + '\n')
    log_file.flush()
    
    train_items = []
    for k, v in train_loss.items():
        if v > 0:  # 0이 아닌 값만 표시
            train_items.append(f"  {k:15s}: {v:8.4f}")
            print(f"  {k:15s}: {v:8.4f}")
            log_file.write(f"  {k:15s}: {v:8.4f}\n")
            log_file.flush()
    
    
    # Val Loss 섹션
    val_section = "\n[VALIDATION]"
    print(val_section)
    log_file.write(val_section + '\n')
    log_file.flush()
    
    for k, v in val_loss.items():
        if v > 0:  # 0이 아닌 값만 표시
            print(f"  {k:15s}: {v:8.4f}")
            log_file.write(f"  {k:15s}: {v:8.4f}\n")
            log_file.flush()    

def save_heatmap(original, reconstructed, save_path, idx, alpha=0.5, cmap='jet', mask=None):
    """
    원본 이미지와 재구성 이미지의 차이를 히트맵으로 시각화
    
    Args:
        original: 원본 이미지 [H, W] 또는 [1, H, W]
        reconstructed: 재구성 이미지 [H, W] 또는 [1, H, W]
        save_path: 저장 경로
        idx: 이미지 인덱스
        alpha: 히트맵 오버레이 투명도 (0-1)
        cmap: 컬러맵 ('jet', 'hot', 'viridis', 'plasma' 등)
        mask: 마스크 [H, W] 또는 [1, H, W] (1=폐/심장 영역, 0=배경)
    """
    # 차원 처리
    if len(original.shape) == 3:
        original = original[0]  # [1, H, W] -> [H, W]
    if len(reconstructed.shape) == 3:
        reconstructed = reconstructed[0]  # [1, H, W] -> [H, W]
    
    # numpy 배열로 변환
    if isinstance(original, torch.Tensor):
        original = original.detach().cpu().numpy()
    if isinstance(reconstructed, torch.Tensor):
        reconstructed = reconstructed.detach().cpu().numpy()
    
    # Reconstruction error 계산 (절대값 차이)
    error_map = np.abs(original - reconstructed)
    
    # ===== 마스크 적용: 배경 영역의 error를 0으로 설정 =====
    if mask is not None:
        # 마스크 차원 처리: [B, 1, H, W] -> [H, W] 또는 [1, H, W] -> [H, W]
        if isinstance(mask, torch.Tensor):
            mask = mask.detach().cpu().numpy()
        
        # 차원 처리
        if len(mask.shape) == 4:
            mask = mask[0, 0]  # [B, 1, H, W] -> [H, W] (첫 번째 배치, 첫 번째 채널)
        elif len(mask.shape) == 3:
            mask = mask[0]  # [1, H, W] -> [H, W]
        elif len(mask.shape) == 2:
            pass  # 이미 [H, W] 형태
        else:
            raise ValueError(f"Unexpected mask shape: {mask.shape}")
        
        # 마스크와 error_map의 크기가 일치하는지 확인
        if mask.shape != error_map.shape:
            # 크기가 다르면 리사이즈 시도
            mask = cv2.resize(mask.astype(np.float32), (error_map.shape[1], error_map.shape[0]), interpolation=cv2.INTER_NEAREST)
            mask = (mask > 0.5).astype(np.float32)  # 이진화
        
        # 마스크 값 확인 및 정규화 (0 또는 1로)
        mask = (mask > 0.5).astype(np.float32)
        
        # 마스크 적용: 배경 영역(0)의 error를 0으로 설정
        error_map = error_map * mask
    # =========================================================
    
    # 정규화 (0-1 범위, 마스킹된 영역만 고려)
    if error_map.max() > 0:
        error_map = error_map / error_map.max()
    
    # 원본 이미지도 0-1 범위로 정규화
    if original.max() > 1.0:
        original_norm = original / 255.0
    else:
        original_norm = original.copy()
    
    # 히트맵만 저장
    fig, ax = plt.subplots(figsize=(10, 10))
    im = ax.imshow(error_map, cmap=cmap, interpolation='bilinear')
    ax.axis('off')
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(os.path.join(save_path, 'heatmap_%03d.jpg' % idx), 
                bbox_inches='tight', pad_inches=0, dpi=150)
    plt.close()
    
    # 원본 이미지 위에 히트맵 오버레이
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(original_norm, cmap='gray')
    im = ax.imshow(error_map, cmap=cmap, alpha=alpha, interpolation='bilinear')
    ax.axis('off')
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(os.path.join(save_path, 'overlay_%03d.jpg' % idx), 
                bbox_inches='tight', pad_inches=0, dpi=150)
    plt.close()

def save_image(path, data, save_heatmaps=False):
    """
    이미지와 히트맵 저장
    
    Args:
        path: 저장 경로
        data: (reconstructed, original) 또는 (reconstructed, original, mask) 튜플의 iterable
        save_heatmaps: 히트맵 저장 여부 (기본값: False, validation 평가 시에만 True로 설정)
    """
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)
    for idx, item in enumerate(data):
        # 데이터 구조 확인: (reconstructed, original) 또는 (reconstructed, original, mask)
        if len(item) == 3:
            img, target, mask = item
        else:
            img, target = item
            mask = None
        
        # 원본 이미지와 재구성 이미지 저장
        plt.imsave(os.path.join(path, '%03d.jpg' % idx), img[0], cmap='gray')
        plt.imsave(os.path.join(path, 'input_%03d.jpg' % idx), target[0], cmap='gray')
        
        # 히트맵 저장 (옵션, 마스크 포함)
        if save_heatmaps:
            save_heatmap(target, img, path, idx, alpha=0.5, cmap='jet', mask=mask)
