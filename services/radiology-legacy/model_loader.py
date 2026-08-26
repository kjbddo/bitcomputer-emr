"""
모델 로더 - eval.py와 동일한 방식으로 모델 로드 및 추론
"""
import sys
import torch
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
import importlib
from scipy.special import expit

from config import MODEL_DIR, DEFAULT_MEAN, DEFAULT_STD, DEFAULT_THRESHOLD
from threshold_loader import load_threshold_from_evaluation, load_mean_std_from_evaluation


class AnomalyDetector:
    """이상 탐지 모델 클래스 - eval.py와 동일한 방식"""
    
    def __init__(self, checkpoint_dir: Path):
        """
        Args:
            checkpoint_dir: 체크포인트가 있는 디렉토리 경로
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        
        # 모델 폴더를 경로에 추가 (eval.py와 동일)
        self._add_to_path(self.checkpoint_dir)
        
        # Config 로드 (eval.py와 동일)
        self.CONFIG = self._load_config()
        
        # 모델 로드 (eval.py와 동일)
        self.model = self._load_model()
        self.discriminator = self._load_discriminator()
        
        # Threshold 설정 (평가 결과에서 로드, 없으면 기본값 사용)
        eval_threshold = load_threshold_from_evaluation(self.checkpoint_dir)
        self.threshold = eval_threshold if eval_threshold is not None else DEFAULT_THRESHOLD
        
        # Mean/Std 설정 (평가 결과에서 로드, 없으면 기본값 사용)
        # 주의: threshold는 확률 변환 후 값에 대한 threshold이므로,
        # 같은 mean/std를 사용해야 threshold가 올바르게 적용됨
        eval_mean_std = load_mean_std_from_evaluation(self.checkpoint_dir)
        if eval_mean_std is not None:
            self.mean, self.std = eval_mean_std
            print(f"✅ 평가 결과에서 mean/std 로드: mean={self.mean:.6f}, std={self.std:.6f}")
        else:
            self.mean = DEFAULT_MEAN
            self.std = DEFAULT_STD
            print(f"⚠️  평가 결과를 찾을 수 없어 기본 mean/std를 사용합니다: mean={self.mean:.6f}, std={self.std:.6f}")
        
        if eval_threshold is None:
            print(f"⚠️  평가 결과를 찾을 수 없어 기본 threshold({self.threshold:.6f})를 사용합니다.")
        
        print(f"✅ 모델 초기화 완료 (Device: {self.device}, Threshold: {self.threshold:.6f})")
    
    def _add_to_path(self, path: Path) -> None:
        """경로를 sys.path에 추가 (중복 방지)"""
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        
        # AI_BackEnd 루트도 경로에 추가 (models/, configs/, dataloader/ 접근용)
        root_path = path.parent
        root_str = str(root_path)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
    
    def _load_config(self):
        """Config 모듈 로드 - eval.py와 동일"""
        # eval.py: CONFIG = importlib.import_module('checkpoints.'+args.exp+'.config').Config()
        # 우리는 checkpoint_dir이 이미 checkpoints/exp 폴더이므로
        import importlib.util
        config_path = self.checkpoint_dir / 'config.py'
        if not config_path.exists():
            raise FileNotFoundError(f"Config 파일을 찾을 수 없습니다: {config_path}")
        
        spec = importlib.util.spec_from_file_location("model_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        
        # configs.base는 이미 AI_BackEnd/configs/base.py에 있으므로 모킹 불필요
        # dataloader도 이미 AI_BackEnd/dataloader/에 있으므로 모킹 불필요
        
        spec.loader.exec_module(config_module)
        config = config_module.Config()
        return config
    
    def _load_model(self) -> torch.nn.Module:
        """SQUID 모델 로드 - eval.py와 동일"""
        # eval.py: MODULE = importlib.import_module('checkpoints.'+args.exp+'.squid')
        import importlib.util
        squid_path = self.checkpoint_dir / 'squid.py'
        if not squid_path.exists():
            raise FileNotFoundError(f"SQUID 모델 파일을 찾을 수 없습니다: {squid_path}")
        
        spec = importlib.util.spec_from_file_location("squid", squid_path)
        squid_module = importlib.util.module_from_spec(spec)
        sys.modules['squid'] = squid_module
        spec.loader.exec_module(squid_module)
        
        # eval.py: model = MODULE.AE(1, 32, CONFIG.shrink_thres, ...)
        model = squid_module.AE(
            1, 32, self.CONFIG.shrink_thres,
            num_slots=self.CONFIG.num_slots,
            num_patch=self.CONFIG.num_patch,
            level=self.CONFIG.level,
            ratio=self.CONFIG.mask_ratio,
            initial_combine=self.CONFIG.initial_combine,
            drop=self.CONFIG.drop,
            dist=self.CONFIG.dist,
            memory_channel=self.CONFIG.memory_channel,
            mem_num_slots=self.CONFIG.mem_num_slots,
            ops=self.CONFIG.ops,
            decoder_memory=self.CONFIG.decoder_memory
        ).to(self.device)
        
        # eval.py: ckpt = torch.load(os.path.join('checkpoints',args.exp,'model.pth'))
        checkpoint_path = self.checkpoint_dir / 'model.pth'
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"모델 체크포인트를 찾을 수 없습니다: {checkpoint_path}")
        
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
        model.load_state_dict(checkpoint)
        model.eval()
        
        return model
    
    def _load_discriminator(self) -> torch.nn.Module:
        """Discriminator 모델 로드 - eval.py와 동일"""
        # eval.py: discriminator = build_disc(CONFIG)
        # tools.py의 build_disc 함수와 동일하게 구현
        import importlib.util
        disc_path = self.checkpoint_dir / 'discriminator.py'
        if not disc_path.exists():
            raise FileNotFoundError(f"Discriminator 파일을 찾을 수 없습니다: {disc_path}")
        
        spec = importlib.util.spec_from_file_location("discriminator", disc_path)
        disc_module = importlib.util.module_from_spec(spec)
        sys.modules['discriminator'] = disc_module
        spec.loader.exec_module(disc_module)
        disc_type = getattr(self.CONFIG, 'discriminator_type', 'basic')
        
        if disc_type == 'basic':
            discriminator = disc_module.SimpleDiscriminator(size=self.CONFIG.size).to(self.device)
        else:
            raise ValueError(f"지원하지 않는 discriminator_type: {disc_type}")
        
        # eval.py: ckpt = torch.load(os.path.join('checkpoints',args.exp,'discriminator.pth'))
        checkpoint_path = self.checkpoint_dir / 'discriminator.pth'
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Discriminator 체크포인트를 찾을 수 없습니다: {checkpoint_path}")
        
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
        discriminator.load_state_dict(checkpoint)
        discriminator.eval()
        
        return discriminator
    
    def predict(self, img_tensor: torch.Tensor, mask: Optional[torch.Tensor] = None) -> Dict[str, Any]:
        """
        이미지에 대한 이상 탐지 수행 - eval.py의 test() 함수와 동일
        
        Args:
            img_tensor: 전처리된 이미지 텐서 [1, 1, H, W]
            mask: 마스크 텐서 [1, 1, H, W] (선택적)
        
        Returns:
            dict: {
                'is_anomaly': bool,
                'score': float,
                'raw_score': float,
                'reconstructed': np.ndarray  # [C, H, W] = [1, H, W]
            }
        """
        self.model.eval()
        self.discriminator.eval()
        
        img_tensor = img_tensor.to(self.device)
        if mask is not None:
            mask = mask.to(self.device)
        
        with torch.no_grad():
            # eval.py: out = model(img)
            out = self.model(img_tensor)
            reconstructed = out['recon']
            
            # eval.py: ROI 마스킹: 폐와 심장 영역만 discriminator에 입력
            if mask is not None:
                if mask.shape[1] == 1 and reconstructed.shape[1] > 1:
                    mask_expanded = mask.expand_as(reconstructed)
                else:
                    mask_expanded = mask
                fake_recon_masked = reconstructed * mask_expanded
            else:
                fake_recon_masked = reconstructed
            
            # eval.py: fake_v = discriminator(fake_recon_masked)
            fake_v = self.discriminator(fake_recon_masked)
            raw_score = fake_v.detach().cpu().numpy()[0]
        
        # ===== 이상 탐지 로직 (alert.evaluate와 동일) =====
        # 1. Score 정규화: train_loader에서 계산된 mean/std 사용
        # 2. 확률 변환: sigmoid 함수를 사용하여 0-1 범위로 변환
        # 3. Threshold 비교: 확률 변환된 값과 threshold 비교
        score_normalized = (raw_score - self.mean) / (self.std + 1e-8)
        score_prob = 1.0 - expit(score_normalized)  # 1이 anomaly, 0이 normal
        
        # 이상 여부 판정
        # threshold는 평가 시 최적 정확도로 계산된 값 (확률 변환 후 값에 대한 threshold)
        is_anomaly = score_prob >= self.threshold
        
        # 재구성 이미지 추출 (0-1 범위, 정규화되지 않은 상태)
        reconstructed_np = reconstructed[0].detach().cpu().numpy()  # [C, H, W] = [1, H, W]
        
        return {
            'is_anomaly': bool(is_anomaly),
            'score': float(score_prob),  # 확률 변환된 값 (0-1 범위, 1이 anomaly)
            'raw_score': float(raw_score),  # discriminator의 raw 출력값
            'reconstructed': reconstructed_np  # [C, H, W] = [1, H, W], 0-1 범위
        }
