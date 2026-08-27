import sys
sys.path.insert(0, '..')

import torch
from dataloader.dataloader_chexpert import CheXpert
from configs.base import BaseConfig

class Config(BaseConfig):
    def __init__(self):
        super(Config, self).__init__()

        #---------------------
        # Training Parameters
        #---------------------
        self.print_freq = 10
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        self.epochs = 200
        self.lr = 1e-4 # learning rate
        self.batch_size = 48
        self.test_batch_size = 2
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR
        self.scheduler_args = dict(T_max=300, eta_min=self.lr*0.5)

        # GAN
        self.gan_lr = 1e-4
        self.discriminator_type = 'basic'
        self.enbale_gan = 0 #100=> gan 활성화 0=> gan 비활성화
        self.lambda_gp = 10.
        # ===== 이미지 크기 256 변경 =====
        # 원본 (128x128): self.size = 4  # (128 / 32 = 4)
        # 변경 (256x256): discriminator size = img_size / 32
        self.size = 8  # discriminator size: img_size / 32 (256 / 32 = 8)
        # =================================
        self.n_critic = 2
        self.sample_interval = 1000
        self.scheduler_d = torch.optim.lr_scheduler.CosineAnnealingLR
        self.scheduler_args_d = dict(T_max=200, eta_min=self.lr*0.2)

        # model
        # ===== num_patch=4로 변경 =====
        # num_patch=2: 4개 패치 (2x2), 각 128x128
        # num_patch=4: 16개 패치 (4x4), 각 64x64 (128x128 설정과 동일한 패치 크기)
        self.num_patch = 4
        # =================================
        self.level = 4 #
        self.shrink_thres = 5
        self.initial_combine = 2
        self.drop = 0.
        self.dist = True
        self.num_slots = 200 # 200 
        self.mem_num_slots = 200 # 200
        # ===== num_patch=4로 변경에 따른 memory_channel 수정 =====
        # num_patch=4일 때:
        #   - 패치 크기: 256/4 = 64, feature map: 64/16 = 4x4
        #   - bottleneck_conv1 출력: [B*16, 128, 4, 4]
        #   - view 후 차원: 128 * 4 * 4 = 2048
        #   - memory_channel = 2048 (128x128 설정과 동일)
        self.memory_channel = 2048  # num_patch=4일 때 feature 차원
        self.img_size = 256  # 이미지 입력 크기 (256x256)
        # =================================
        self.mask_ratio = 0.95
        self.ops = ['concat', 'concat', 'none', 'none']
        
        # Decoder Memory 설정
        # ===== num_patch=4로 변경 =====
        # num_patch=4일 때: num_memory = 4**2 = 16
        # Decoder 순서: up_blocks[i]를 먼저 적용하고 그 다음 memory_blocks[-1-i]를 적용
        # MemoryMatrixBlock에서 window_size = feature_map_size // sqrt(num_memory) = feature_map_size // 4
        # 각 window의 flatten 차원 = window_size**2 * C
        # multiplier = (window_size**2 * C) / filter_list[i]
        # 
        # Decoder 단계별 (up_blocks 적용 후):
        #   - decoder_memory[3] (i=0): up_blocks[0] 후 8x8, C=256, window_size=2 → flatten=1024 → multiplier=4
        #   - decoder_memory[2] (i=1): up_blocks[1] 후 16x16, C=128, window_size=4 → flatten=2048 → multiplier=16
        import models.memory as Memory
        self.decoder_memory = [None, 
                               None, 
                               dict(type='MemoryMatrixBlock', multiplier=16, num_memory=self.num_patch**2),  # level 2: 128*16=2048
                               dict(type='MemoryMatrixBlock', multiplier=4, num_memory=self.num_patch**2)]   # level 3: 256*4=1024
        # =================================

        # loss weight
        self.t_w = 0.01
        self.recon_w = 10.
        self.dist_w = 0.001
        self.g_w = 0.005
        self.d_w = 0.005

        # misc
        self.disable_tqdm = True#False
        self.dataset_name = 'chexpert'
        self.early_stop = 200
        self.limit = None  # None이면 전체 사용 -> 200번째 배치까지 처리
        self.data_type = 'pa'
        
        # ===== 마스킹 설정 =====
        # 폐와 심장 영역만 확인하도록 마스킹 (HybridGNetSegmenter 활용)
        self.enable_masking = True  # 마스킹 기능 활성화 여부
        # =======================
        
        # ===== zhanglab 데이터 경로 설정 =====
        # chest_xray/zhanglab 폴더에서 추가 데이터 로드
        from pathlib import Path
        # configs/chexpert_best.py -> anomaly_squid -> chest_xray
        config_dir = Path(__file__).parent
        anomaly_squid_dir = config_dir.parent
        chest_xray_dir = anomaly_squid_dir.parent
        zhanglab_path = chest_xray_dir / 'zhanglab'
        
        if zhanglab_path.exists():
            self.zhanglab_root = str(zhanglab_path)
            print(f"zhanglab 데이터 경로: {self.zhanglab_root}")
        else:
            self.zhanglab_root = None
            print(f"Warning: zhanglab 데이터 경로를 찾을 수 없습니다: {zhanglab_path}")
        # =====================================

        # 데이터로더 생성 (archive 구조에 맞게, zhanglab 데이터 포함)
        self.train_dataset = CheXpert(self.data_root, train=True, 
                           img_size=(self.img_size, self.img_size), data_type=self.data_type,
                           enable_masking=self.enable_masking, device=self.device,
                           zhanglab_root=self.zhanglab_root)
        
        self.train_loader = torch.utils.data.DataLoader(self.train_dataset, batch_size=self.batch_size, shuffle=True, num_workers=32, drop_last=False)
        
        self.val_dataset = CheXpert(self.data_root, train=False, 
                            img_size=(self.img_size, self.img_size), full=True, data_type=self.data_type,
                            enable_masking=self.enable_masking, device=self.device,
                            zhanglab_root=self.zhanglab_root)
        self.val_loader = torch.utils.data.DataLoader(self.val_dataset, batch_size=self.batch_size, shuffle=False, num_workers=32, drop_last=False)
        
        # test는 val과 동일하게 사용 (필요시 별도 설정 가능)
        self.test_dataset = self.val_dataset
        self.test_loader = self.val_loader
