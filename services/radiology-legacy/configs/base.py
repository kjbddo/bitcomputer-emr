import sys
import torch
from pathlib import Path

# 프로젝트 루트 경로
project_root = Path(__file__).parent.parent.parent.parent.parent

class BaseConfig():
    def __init__(self, require_data_root=True):
        """
        Args:
            require_data_root: True면 데이터 폴더가 없을 때 에러 발생, False면 None으로 설정 (추론 시 사용)
        """
        #---------------------
        # Training Parameters
        #---------------------
        # 데이터 경로 설정 (archive_pa 우선, 없으면 archive 사용)
        archive_pa_path = project_root / 'mvtec_root' / 'chest_xray' / 'archive_pa'
        archive_path = project_root / 'mvtec_root' / 'chest_xray' / 'archive'
        
        if archive_pa_path.exists() and (archive_pa_path / 'train.csv').exists():
            self.data_root = str(archive_pa_path)
            if require_data_root:
                print(f"데이터 경로: archive_pa 사용")
        elif archive_path.exists() and (archive_path / 'train.csv').exists():
            self.data_root = str(archive_path)
            if require_data_root:
                print(f"데이터 경로: archive 사용 (archive_pa가 없어서 archive 사용)")
        else:
            if require_data_root:
                # 학습 시에는 데이터 폴더가 필수
                raise FileNotFoundError(
                    f"데이터 폴더를 찾을 수 없습니다.\n"
                    f"다음 경로 중 하나가 필요합니다:\n"
                    f"  - {archive_pa_path}\n"
                    f"  - {archive_path}\n"
                    f"또는 CSV 파일이 있는 경로를 확인하세요."
                )
            else:
                # 추론 시에는 데이터 폴더가 없어도 됨
                self.data_root = None
        
        self.print_freq = 10
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        self.epochs = 400
        self.lr = 1e-4
        self.batch_size = 16
        self.test_batch_size = 2
        self.opt = torch.optim.Adam
        self.scheduler = torch.optim.lr_scheduler.MultiStepLR
        self.scheduler_args = dict(milestones=[200, 300], gamma=0.2)

        # GAN
        self.discriminator_type = 'basic'
        self.enbale_gan = 0 #100
        self.lambda_gp = 10
        self.size = 4
        self.n_critic = 1
        self.sample_interval = 1000
        self.scheduler_d = torch.optim.lr_scheduler.MultiStepLR
        self.scheduler_args_d = dict(milestones=[200-self.enbale_gan, 300-self.enbale_gan], gamma=0.2)

        # model
        self.num_patch = 2 #4
        self.level = 4 #
        self.shrink_thres = 0.0005
        self.initial_combine = 2
        self.drop = 0.0
        self.dist = True
        self.num_slots = 1000
        self.mem_num_slots = 500
        self.memory_channel = 2048
        self.img_size = 128
        self.mask_ratio = 0.95
        self.ops = ['concat', 'concat', 'none', 'none']
        self.decoder_memory = [None, 
                               None, 
                               dict(type='MemoryMatrixBlock', multiplier=64, num_memory=self.num_patch**2),
                               dict(type='MemoryMatrixBlock', multiplier=16, num_memory=self.num_patch**2)]

        # loss weight
        self.t_w = 0.5
        self.recon_w = 1.
        self.dist_w = 0.1
        self.g_w = 0.0005
        self.d_w = 1.

        # misc
        self.disable_tqdm = True
        self.dataset_name = 'zhang'
        self.early_stop = 200
        self.limit = None

        # alert
        self.alert = None#Alert(lambda1=1., lambda2=1.)
