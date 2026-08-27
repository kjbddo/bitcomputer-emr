"""
Threshold 및 Mean/Std 로더 - 평가 결과에서 값 로드
"""
import re
from pathlib import Path
from typing import Optional, Tuple


def load_mean_std_from_evaluation(checkpoint_dir: Path) -> Optional[Tuple[float, float]]:
    """
    평가 결과에서 mean/std 값을 로드
    
    Args:
        checkpoint_dir: 체크포인트 디렉토리 경로
        
    Returns:
        (mean, std) 튜플 또는 None (찾을 수 없는 경우)
    """
    checkpoint_dir = Path(checkpoint_dir)
    
    # visualizations 폴더 찾기
    visualizations_dir = checkpoint_dir / 'visualizations'
    if not visualizations_dir.exists():
        return None
    
    # 가장 최근 visualizations 폴더 찾기
    viz_folders = sorted([d for d in visualizations_dir.iterdir() if d.is_dir()], reverse=True)
    if not viz_folders:
        return None
    
    # 가장 최근 폴더의 model_config.txt 읽기
    latest_viz_dir = viz_folders[0]
    config_file = latest_viz_dir / 'model_config.txt'
    
    if not config_file.exists():
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Score Normalization Mean/Std 찾기
        # 형식: "  Score Normalization Mean: 0.226190"
        # 형식: "  Score Normalization Std: 1.577745"
        mean_pattern = r'Score Normalization Mean:\s*([\d.]+)'
        std_pattern = r'Score Normalization Std:\s*([\d.]+)'
        
        mean_match = re.search(mean_pattern, content)
        std_match = re.search(std_pattern, content)
        
        if mean_match and std_match:
            mean = float(mean_match.group(1))
            std = float(std_match.group(1))
            print(f"✅ 평가 결과에서 Score Normalization Mean/Std 로드: mean={mean:.6f}, std={std:.6f} (파일: {config_file})")
            return (mean, std)
        else:
            print(f"⚠️  model_config.txt에서 Score Normalization Mean/Std를 찾을 수 없습니다: {config_file}")
            return None
            
    except Exception as e:
        print(f"⚠️  mean/std 로드 실패: {e}")
        return None


def load_threshold_from_evaluation(checkpoint_dir: Path) -> Optional[float]:
    """
    평가 결과에서 threshold 값을 로드
    
    Args:
        checkpoint_dir: 체크포인트 디렉토리 경로
        
    Returns:
        threshold 값 또는 None (찾을 수 없는 경우)
    """
    checkpoint_dir = Path(checkpoint_dir)
    
    # visualizations 폴더 찾기
    visualizations_dir = checkpoint_dir / 'visualizations'
    if not visualizations_dir.exists():
        return None
    
    # 가장 최근 visualizations 폴더 찾기
    viz_folders = sorted([d for d in visualizations_dir.iterdir() if d.is_dir()], reverse=True)
    if not viz_folders:
        return None
    
    # 가장 최근 폴더의 model_config.txt 읽기
    latest_viz_dir = viz_folders[0]
    config_file = latest_viz_dir / 'model_config.txt'
    
    if not config_file.exists():
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # threshold 값 찾기
        # 형식: "  threshold: 0.8518987894058228"
        pattern = r'threshold:\s*([\d.]+)'
        match = re.search(pattern, content)
        
        if match:
            threshold = float(match.group(1))
            print(f"✅ 평가 결과에서 threshold 로드: {threshold:.6f} (파일: {config_file})")
            return threshold
        else:
            print(f"⚠️  model_config.txt에서 threshold를 찾을 수 없습니다: {config_file}")
            return None
            
    except Exception as e:
        print(f"⚠️  threshold 로드 실패: {e}")
        return None
