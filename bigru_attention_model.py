import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils.rnn import pack_padded_sequence
class bigru_attention(nn.Module):
    def __init__(
            self,
            vocab_size,
            output_dim,
            n_layers=2,
            pad_idx=None,
            hidden_dim=128,
            embed_dim=300,
            dropout=0.1,
            bidirectional=True,
    ):
        super(bigru_attention, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        # 双向GRU，//操作为了与后面的Attention操作维度匹配，hidden_dim要取偶数！
        self.bigru = nn.GRU(embed_dim, hidden_dim//2, num_layers=n_layers, bidirectional=bidirectional,dropout=dropout)
        # 由nn.Parameter定义的变量都为requires_grad=True状态
        self.weight_W = nn.Parameter(torch.Tensor(hidden_dim, hidden_dim))
        self.weight_proj = nn.Parameter(torch.Tensor(hidden_dim, 1))
        # 二分类
        self.fc = nn.Linear(hidden_dim, output_dim)

        nn.init.uniform_(self.weight_W, -0.1, 0.1)
        nn.init.uniform_(self.weight_proj, -0.1, 0.1)

    def forward(self, sentence):
        embeds = self.embedding(sentence)  # [seq_len, bs, emb_dim]
        gru_out, _ = self.bigru(embeds)  # [seq_len, bs, hid_dim]
        x = gru_out.permute(1, 0, 2)
        # # # Attention过程，与上图中三个公式对应
        u = torch.tanh(torch.matmul(x, self.weight_W))
        att = torch.matmul(u, self.weight_proj)
        att_score = F.softmax(att, dim=1)
        scored_x = x * att_score
        # # # Attention过程结束

        feat = torch.sum(scored_x, dim=1)
        y = self.fc(feat)
        return y