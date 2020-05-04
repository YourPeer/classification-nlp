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
        # ˫��GRU��//����Ϊ��������Attention����ά��ƥ�䣬hidden_dimҪȡż����
        self.bigru = nn.GRU(embed_dim, hidden_dim//2, num_layers=n_layers, bidirectional=bidirectional,dropout=dropout)
        # ��nn.Parameter����ı�����Ϊrequires_grad=True״̬
        self.weight_W = nn.Parameter(torch.Tensor(hidden_dim, hidden_dim))
        self.weight_proj = nn.Parameter(torch.Tensor(hidden_dim, 1))
        # ������
        self.fc = nn.Linear(hidden_dim, output_dim)

        nn.init.uniform_(self.weight_W, -0.1, 0.1)
        nn.init.uniform_(self.weight_proj, -0.1, 0.1)

    def forward(self, sentence):
        embeds = self.embedding(sentence)  # [seq_len, bs, emb_dim]
        gru_out, _ = self.bigru(embeds)  # [seq_len, bs, hid_dim]
        x = gru_out.permute(1, 0, 2)
        # # # Attention���̣�����ͼ��������ʽ��Ӧ
        u = torch.tanh(torch.matmul(x, self.weight_W))
        att = torch.matmul(u, self.weight_proj)
        att_score = F.softmax(att, dim=1)
        scored_x = x * att_score
        # # # Attention���̽���

        feat = torch.sum(scored_x, dim=1)
        y = self.fc(feat)
        return y