# -*- coding: utf-8 -*-
import os
import logging
from typing import List, Dict

import torch
import torch.nn as nn
from torch.optim import Adam
from torchtext.vocab import Vectors
from torchtext.data import BucketIterator
from torch.optim import lr_scheduler
from torch.utils.tensorboard import SummaryWriter

from tqdm import tqdm, trange
from sklearn.metrics import precision_recall_fscore_support

from args import get_args
from model import TextClassifier
from bigru_attention_model import bigru_attention
from tool import build_and_cache_dataset, save_model

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def train(args, writer,is_train=True):

    # Build train dataset
    fields, train_dataset = build_and_cache_dataset(args, mode='train')
    # for i in range(5):
    #     print(train_dataset[i].category,train_dataset[i].news)
    # return

    # Build vocab
    ID, CATEGORY, NEWS = fields
    vectors = Vectors(name=args.embed_path, cache=args.data_dir)
    # NOTE: use train_dataset to build vocab!
    NEWS.build_vocab(
        train_dataset,
        max_size=args.vocab_size,
        vectors=vectors,
        unk_init=torch.nn.init.xavier_normal_,
    )
    CATEGORY.build_vocab(train_dataset)

    # print("查找第1000个单词:"+NEWS.vocab.itos[1000])
    # print("查找单词‘每个’的索引："+str(NEWS.vocab.stoi[r'每个']))
    # print("词向量矩阵的维度:"+str(NEWS.vocab.vectors.shape))
    # word_vec = NEWS.vocab.vectors[NEWS.vocab.stoi['每个']]
    # print("单词‘每个’的词向量为："+str(word_vec))
    # return

    # model = TextClassifier(
    #     vocab_size=len(NEWS.vocab),
    #     output_dim=args.num_labels,
    #     pad_idx=NEWS.vocab.stoi[NEWS.pad_token],
    #     dropout=args.dropout,
    # )

    #使用双向gru+attetion机制模型
    model = bigru_attention(
        vocab_size=len(NEWS.vocab),
        output_dim=args.num_labels,
        pad_idx=NEWS.vocab.stoi[NEWS.pad_token],
        dropout=args.dropout,
    )

    # Init embeddings for model
    model.embedding.from_pretrained(NEWS.vocab.vectors)

    bucket_iterator = BucketIterator(
        train_dataset,
        batch_size=args.train_batch_size,
        sort_within_batch=True,
        shuffle=True,
        sort_key=lambda x: len(x.news),
        device=args.device,
    )
    f1_score = 0
    if os.listdir("output_dir"):
        f1_score=float(os.listdir("output_dir")[0].split("_")[1].split(".p")[0])
        model.load_state_dict(torch.load("output_dir/"+os.listdir("output_dir")[0]))
    model.to(args.device)
    criterion = nn.CrossEntropyLoss()
    optimizer = Adam(model.parameters(),
                     lr=args.learning_rate,
                     eps=args.adam_epsilon)
    # scheduler = lr_scheduler.OneCycleLR(optimizer,
    #                        max_lr=args.learning_rate,
    #                        epochs=args.num_train_epochs,
    #                        steps_per_epoch=len(bucket_iterator))
    #scheduler = lr_scheduler.StepLR(optimizer, step_size=4, gamma=0.1,last_epoch = -1 )

    global_step = 0
    model.zero_grad()


    if is_train:
        train_trange = trange(0, args.num_train_epochs, desc="Train epoch")
        for _ in train_trange:
            epoch_iterator = tqdm(bucket_iterator, desc='Training')
            results_f1_score=0
            for step, batch in enumerate(epoch_iterator):
                model.train()

                news, news_lengths = batch.news #new.size() [8  ,64]
                category = batch.category #category.size() [64]
                #preds = model(news, news_lengths)
                preds = model(news)
                loss = criterion(preds, category)
                loss.backward()
                #optimizer.zero_grad()
                optimizer.step()
                #scheduler.step()
                # Logging
                writer.add_scalar('Train/Loss', loss.item(), global_step)
                # writer.add_scalar('Train/lr',
                #                   scheduler.get_last_lr()[0], global_step)
                # NOTE: Update model, optimizer should update before scheduler



                global_step += 1

                # NOTE:Evaluate
                if args.logging_steps > 0 and global_step % args.logging_steps == 0:
                    results = evaluate(args, model, CATEGORY.vocab, NEWS.vocab)
                    results_f1_score=results['f1']
                    for key, value in results.items():
                        writer.add_scalar("Eval/{}".format(key), value,
                                          global_step)

                # NOTE: save model
                # if args.save_steps > 0 and global_step % args.save_steps == 0:
                #     save_model(args, model, optimizer, scheduler, global_step)
                if results_f1_score>f1_score:
                    try:
                        os.remove("output_dir/model_"+str(f1_score)+".pt")
                    except:
                        print("None!")
                    torch.save(model.state_dict(), "output_dir/model_"+str(results_f1_score)+".pt")
                    f1_score=results_f1_score
                    print("So far the best score is:"+str(f1_score)+"+++++++++++++++++++++++++++++++")
        writer.close()
    else:
        test(args, model, CATEGORY.vocab, NEWS.vocab)


def evaluate(args, model, category_vocab, example_vocab, mode='dev'):
    fields, eval_dataset = build_and_cache_dataset(args, mode=mode)
    bucket_iterator = BucketIterator(
        eval_dataset,
        train=False,
        batch_size=args.eval_batch_size,
        sort_within_batch=True,
        sort_key=lambda x: len(x.news),
        device=args.device,
    )
    ID, CATEGORY, NEWS = fields
    CATEGORY.vocab = category_vocab
    NEWS.vocab = example_vocab
    logger.info("***** Running evaluation *****")
    logger.info("  Num examples = %d", len(eval_dataset))
    logger.info("  Batch size = %d", args.eval_batch_size)

    # NOTE: Eval!
    model.eval()
    criterion = nn.CrossEntropyLoss()
    eval_loss, eval_steps = 0.0, 0
    labels_list, preds_list = [], []
    for batch in tqdm(bucket_iterator, desc='Evaluation'):
        news, news_lengths = batch.news
        labels = batch.category
        with torch.no_grad():
            # logits = model(news, news_lengths)
            logits = model(news)
            loss = criterion(logits, labels)
            eval_loss += loss.item()

        eval_steps += 1
        preds = torch.argmax(logits, dim=1)
        preds_list.append(preds)
        labels_list.append(labels)

    y_true = torch.cat(labels_list).detach().cpu().numpy()
    y_pred = torch.cat(preds_list).detach().cpu().numpy()
    precision, recall, f1_score, _ = precision_recall_fscore_support(
        y_true, y_pred, average='micro')

    # Write into tensorboard
    # TODO: recore false-pos and false-neg samples.
    results = {
        'loss': eval_loss / eval_steps,
        'f1': f1_score,
        'precision': precision,
        'recall': recall
    }
    msg = f'*** Eval: loss {loss}, f1 {f1_score}, precision {precision}, recall {recall}'
    logger.info(msg)
    return results

def test(args, model, category_vocab, example_vocab, mode='test'):
    fields, test_dataset = build_and_cache_dataset(args, mode=mode)
    bucket_iterator = BucketIterator(
        test_dataset,
        train=False,
        batch_size=args.eval_batch_size,
        sort_within_batch=True,
        sort_key=lambda x: len(x.news),
        device=args.device,
    )
    ID, CATEGORY, NEWS = fields
    CATEGORY.vocab = category_vocab
    NEWS.vocab = example_vocab

    model.eval()
    criterion = nn.CrossEntropyLoss()
    eval_loss, eval_steps = 0.0, 0
    labels_list, preds_list = [], []
    for batch in tqdm(bucket_iterator, desc='test'):
        news, news_lengths = batch.news
        labels = batch.category
        with torch.no_grad():
            # logits = model(news, news_lengths)
            logits = model(news)
            loss = criterion(logits, labels)
            eval_loss += loss.item()

        eval_steps += 1
        preds = torch.argmax(logits, dim=1)
        preds_list.append(preds)
        labels_list.append(labels)

    y_true = torch.cat(labels_list).detach().cpu().numpy()
    y_pred = torch.cat(preds_list).detach().cpu().numpy()
    import pandas as pd
    classes_map={0:'news_culture', 1:'news_car', 2:'news_edu', 3:'news_house', 4:'news_agriculture'}
    test_dict={"predict value":y_pred,"ture value":y_true,"predict class":[classes_map[i] for i in y_pred],"ture class":[classes_map[i] for i in y_true]}
    test_dict_df = pd.DataFrame(test_dict)
    test_dict_df.to_csv("test_data.csv")
    precision, recall, f1_score, _ = precision_recall_fscore_support(
        y_true, y_pred, average='micro')

    # Write into tensorboard
    # TODO: recore false-pos and false-neg samples.
    results = {
        'loss': eval_loss / eval_steps,
        'f1': f1_score,
        'precision': precision,
        'recall': recall
    }
    msg = f'*** test: loss {loss}, f1 {f1_score}, precision {precision}, recall {recall}'
    logger.info(msg)
    return results


def main():
    args = get_args()
    writer = SummaryWriter()

    # Check output dir
    if not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)

    # if os.path.exists(args.output_dir) \
    #         and os.listdir(args.output_dir) \
    #         and  args.overwrite_output_dir:
    #     raise ValueError(
    #         f"Output directory ({args.output_dir}) already exists and is not empty. "
    #         "Use --overwrite_output_dir to overcome.")

    # Set device
    device = "cuda" if torch.cuda.is_available() and not args.no_cuda else "cpu"
    args.device = torch.device(device)
    logger.info("Process device: %s", device)

    train(args, writer,is_train=False)


if __name__ == "__main__":
    main()