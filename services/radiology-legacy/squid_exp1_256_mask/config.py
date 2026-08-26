import sys
sys.path.insert(0, '..')

import torch
# 추론 시에는 데이터로더가 필요 없으므로 import 제거
# from dataloader.dataloader_chexpert import CheXpert
from configs.base import BaseConfig

class Config(BaseConfig):
    def __init__(self):
        # 추론 시에는 데이터로더가 필요 없으므로 require_data_root=False
        super(Config, self).__init__(require_data_root=False)

        #--------------------- 
        # Training Parameters (추론 시 사용되지 않지만 모델 구조 호환성을 위해 유지)
        #---------------------
        self.print_freq = 10
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        # 학습 관련 파라미터 (추론 시 사용 안 함)
        self.epochs = 200
        self.lr = 1e-4
        self.batch_size = 48
        self.test_batch_size = 2
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR
        self.scheduler_args = dict(T_max=300, eta_min=self.lr*0.5)

        # GAN (추론 시 discriminator만 사용)
        self.gan_lr = 1e-4
        self.discriminator_type = 'basic'  # 추론 시 필요
        self.enbale_gan = 0
        self.lambda_gp = 10.
        # ===== 이미지 크기 256 변경 =====
        # 원본 (128x128): self.size = 4  # (128 / 32 = 4)
        # 변경 (256x256): discriminator size = img_size / 32
        self.size = 8  # discriminator size: img_size / 32 (256 / 32 = 8) - 추론 시 필요
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

        # loss weight (추론 시 사용 안 함, 모델 구조 호환성 유지)
        self.t_w = 0.01
        self.recon_w = 10.
        self.dist_w = 0.001
        self.g_w = 0.005
        self.d_w = 0.005

        # misc (추론 시 사용 안 함)
        self.disable_tqdm = True
        self.dataset_name = 'chexpert'
        self.early_stop = 200
        self.limit = None
        self.data_type = 'pa'
        
        # ===== 마스킹 설정 =====
        # 폐와 심장 영역만 확인하도록 마스킹 (HybridGNetSegmenter 활용)
        self.enable_masking = True  # 마스킹 기능 활성화 여부 - 추론 시 필요
        # =======================
        
        # 추론 시에는 데이터로더와 zhanglab 경로가 필요 없음
        self.zhanglab_root = None
        self.train_dataset = None
        self.train_loader = None
        self.val_dataset = None
        self.val_loader = None
        self.test_dataset = None
        self.test_loader = None
