import os
import torch
import argparse
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import MultiStepLR
from torch.optim import SGD, Adam
from typing import Dict, List
from tqdm import tqdm
import numpy as np
import time
import torch.backends.cudnn as cudnn
import matplotlib.pyplot as plt
import random
from .dataset.utils import Split
from .dataset import config as config_lib
from .dataset import dataset_spec as dataset_spec_lib
from .dataset import pipeline
from .models import __dict__ as all_models
from .methods import __dict__ as all_methods
from .losses import __dict__ as all_losses
from .utils import load_cfg_from_cfg_file, merge_cfg_from_list, AverageMeter, \
                   save_checkpoint, get_model_dir, make_episode_visualization, \
                   load_checkpoint
from .train import get_dataloader

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description='Testing')
    parser.add_argument('--base_config', type=str, required=True, help='Base config file')
    parser.add_argument('--method_config', type=str, default=True, help='Base config file')
    parser.add_argument('--opts', default=None, nargs=argparse.REMAINDER)
    args = parser.parse_args()

    cfg = load_cfg_from_cfg_file(args.base_config)
    cfg.update(load_cfg_from_cfg_file(args.method_config))
    if args.opts is not None:
        cfg = merge_cfg_from_list(cfg, args.opts)
    return cfg


def main(args):

    # ============ Device ================
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_dir = get_model_dir(args)

    # ============ Testing method ================
    method = all_methods[args.method](args=args)

    # ============ Data loaders =========
    _, num_classes_tr = get_dataloader(args=args,
                                       sources=args.train_sources,
                                       episodic=method.episodic_training,
                                       batch_size=args.batch_size,
                                       split=Split["TRAIN"])

    test_loader, num_classes = get_dataloader(args=args,
                                              sources=args.test_sources,
                                              episodic=True,
                                              batch_size=args.test_batch_size,
                                              split=Split["TRAIN"])
    print(f"=> There are {num_classes} classes in the test datasets")

    # ============ Model ================
    model = all_models[args.arch](num_classes=num_classes_tr if args.method != 'MAML' else args.num_ways).to(device)
    load_checkpoint(model, model_dir, type='best')

    # ============ Training loop ============
    model.eval()
    print('Starting testing ...')
    test_acc = 0.
    test_loss = 0.
    with torch.no_grad():
        tqdm_bar = tqdm(test_loader, total=args.test_iter, ascii=True)
        i = 0
        for data in tqdm_bar:
            support, query, support_labels, query_labels = data
            support, support_labels = support.to(device), support_labels.to(device, non_blocking=True)
            query, query_labels = query.to(device), query_labels.to(device, non_blocking=True)

            # ============ Evaluation ============
            loss, soft_preds_q = method(x_s=support,
                                        x_q=query,
                                        y_s=support_labels,
                                        y_q=query_labels,
                                        model=model)
            if args.visu and i % 100 == 0:
                task_id = 0
                root = os.path.join(model_dir, 'visu', 'test')
                os.makedirs(root, exist_ok=True)
                save_path = os.path.join(root, f'{i}.png')
                make_episode_visualization(
                           args,
                           support[task_id].cpu().numpy(),
                           query[task_id].cpu().numpy(),
                           support_labels[task_id].cpu().numpy(),
                           query_labels[task_id].cpu().numpy(),
                           soft_preds_q[task_id].cpu().numpy(),
                           save_path)
            test_acc += (soft_preds_q.argmax(-1) == query_labels).float().mean()
            if loss:
                test_loss += loss
            if i % 10 == 0:
                tqdm_bar.set_description(f'Test Prec@1 {test_acc / (i+1):.3f}  \
                                           Test loss {test_loss / (i+1):.3f}',
                                         )
            if i >= args.test_iter:
                break
            i += 1


if __name__ == '__main__':
    args = parse_args()
    main(args)