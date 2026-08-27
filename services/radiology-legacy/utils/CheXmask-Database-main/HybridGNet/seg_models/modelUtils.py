import torch
from torch import Tensor
from torch.nn import Parameter
from typing import Optional
from torch_geometric.nn.conv import MessagePassing
from torch_geometric.nn.conv.cheb_conv import ChebConv as _ChebConv
from torch_geometric.nn.inits import zeros, normal
from torch_geometric.typing import OptTensor
from torch_geometric.utils import get_laplacian
from torch_geometric.nn.dense.linear import Linear

# We change the default initialization from zeros to a normal distribution
# ChebConv를 완전히 새로 정의하여 propagate() 메서드가 제대로 생성되도록 함
# torch_geometric이 클래스 정의 시점에 message() 메서드의 시그니처를 분석하여
# propagate() 메서드를 동적으로 생성하므로, 상속만으로는 제대로 생성되지 않습니다.
# 따라서 ChebConv를 완전히 새로 정의합니다.
class ChebConv(MessagePassing):
    def __init__(self, in_channels, out_channels, K, normalization='sym', bias=True, **kwargs):
        kwargs.setdefault('aggr', 'add')
        super().__init__(**kwargs)
        
        if in_channels <= 0:
            raise ValueError(f'Expected in_channels to be a positive integer, but got {in_channels}')
        if out_channels <= 0:
            raise ValueError(f'Expected out_channels to be a positive integer, but got {out_channels}')
        if K <= 0:
            raise ValueError(f'Expected K to be a positive integer, but got {K}')
        
        assert normalization in [None, 'sym', 'rw'], 'Invalid normalization'
        
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.K = K
        self.normalization = normalization
        
        self.lins = torch.nn.ModuleList([
            Linear(in_channels, out_channels, bias=False,
                   weight_initializer='uniform') for _ in range(K)
        ])
        
        if bias:
            self.bias = Parameter(torch.empty(out_channels))
        else:
            self.register_parameter('bias', None)
        
        self.reset_parameters()
    
    def reset_parameters(self):
        for lin in self.lins:
            normal(lin, mean=0, std=0.1)
        if self.bias is not None:
            normal(self.bias, mean=0, std=0.1)
    
    def __norm__(
        self,
        edge_index: Tensor,
        num_nodes: Optional[int],
        edge_weight: OptTensor,
        normalization: Optional[str],
        lambda_max: OptTensor = None,
        dtype: Optional[int] = None,
        batch: OptTensor = None,
    ):
        edge_index, edge_weight = get_laplacian(edge_index, edge_weight,
                                                normalization, dtype,
                                                num_nodes)
        assert edge_weight is not None
        
        if lambda_max is None:
            lambda_max = 2.0 * edge_weight.max()
        elif not isinstance(lambda_max, Tensor):
            lambda_max = torch.tensor(lambda_max, dtype=dtype,
                                      device=edge_index.device)
        assert lambda_max is not None
        
        if batch is not None and lambda_max.numel() > 1:
            lambda_max = lambda_max[batch[edge_index[0]]]
        
        edge_weight = (2.0 * edge_weight) / lambda_max
        edge_weight.masked_fill_(edge_weight == float('inf'), 0)
        
        loop_mask = edge_index[0] == edge_index[1]
        edge_weight[loop_mask] -= 1
        
        return edge_index, edge_weight
    
    def forward(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_weight: OptTensor = None,
        batch: OptTensor = None,
        lambda_max: OptTensor = None,
    ) -> Tensor:
        
        edge_index, norm = self.__norm__(
            edge_index,
            x.size(self.node_dim),
            edge_weight,
            self.normalization,
            lambda_max,
            dtype=x.dtype,
            batch=batch,
        )
        
        Tx_0 = x
        Tx_1 = x  # Dummy.
        out = self.lins[0](Tx_0)
        
        # propagate_type: (x: Tensor, norm: Tensor)
        if len(self.lins) > 1:
            Tx_1 = self.propagate(edge_index, x=x, norm=norm, size=None)
            out = out + self.lins[1](Tx_1)
        
        for lin in self.lins[2:]:
            Tx_2 = self.propagate(edge_index, x=Tx_1, norm=norm, size=None)
            Tx_2 = 2. * Tx_2 - Tx_0
            out = out + lin.forward(Tx_2)
            Tx_0, Tx_1 = Tx_1, Tx_2
        
        if self.bias is not None:
            out = out + self.bias
        
        return out
    
    def message(self, x_j: Tensor, norm: Tensor) -> Tensor:
        return norm.view(-1, 1) * x_j

# Pooling from COMA: https://github.com/pixelite1201/pytorch_coma/blob/master/layers.py
class Pool(MessagePassing):
    def __init__(self):
        # source_to_target is the default value for flow, but is specified here for explicitness
        super(Pool, self).__init__(flow='source_to_target', aggr='add')

    def forward(self, x, pool_mat,  dtype=None):
        pool_mat = pool_mat.transpose(0, 1)
        # torch_geometric 2.7.0 호환성: propagate()는 **kwargs를 받으므로 x를 키워드 인자로 전달 가능
        # propagate_type 데코레이터를 사용하여 타입 힌트 제공 (동적 propagate 생성에 필요)
        # propagate_type: (x: Tensor, norm: Tensor)
        out = self.propagate(edge_index=pool_mat._indices(), x=x, norm=pool_mat._values(), size=pool_mat.size())
        return out

    def message(self, x_j: Tensor, norm: Tensor) -> Tensor:
        return norm.view(1, -1, 1) * x_j
    
    
import torch.nn as nn
import torch.nn.functional as F

class residualBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1):
        """
        Args:
          in_channels (int):  Number of input channels.
          out_channels (int): Number of output channels.
          stride (int):       Controls the stride.
        """
        super(residualBlock, self).__init__()

        self.skip = nn.Sequential()

        if stride != 1 or in_channels != out_channels:
          self.skip = nn.Sequential(
            nn.Conv2d(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=stride, bias=False),
            nn.BatchNorm2d(out_channels, track_running_stats=False))
        else:
          self.skip = None

        self.block = nn.Sequential(nn.BatchNorm2d(in_channels, track_running_stats=False),
                                   nn.ReLU(inplace=True),
                                   nn.Conv2d(in_channels, out_channels, 3, padding=1),
                                   nn.BatchNorm2d(out_channels, track_running_stats=False),
                                   nn.ReLU(inplace=True),
                                   nn.Conv2d(out_channels, out_channels, 3, padding=1)
                                   )   

    def forward(self, x):
        identity = x
        out = self.block(x)

        if self.skip is not None:
            identity = self.skip(x)

        out += identity
        out = F.relu(out)

        return out