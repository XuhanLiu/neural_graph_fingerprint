from pathlib import Path
from torch.utils.data import DataLoader, Subset
from NeuralGraph.dataset import MolData, SmileData
from NeuralGraph.model import QSAR, MLP
import torch.nn as nn
import pandas as pd
import numpy as np
import argparse


FP_METHODS = ["morgan", "nfp"]
FP_LEN = 1<<9 # fingerprint length for circular FP

def split_train_valid_test(n, p=0.8, v=0.1, seed=None):
    if seed:
        np.random.seed(seed)
    idx = np.arange(n)
    np.random.shuffle(idx)
    s = int(n*p)
    t = int(n*v)
    # train, valid, test
    return idx[:s], idx[s:(s+t)], idx[(s+t):]


def normalize_array(A):
    mean, std = np.mean(A), np.std(A)
    def norm_func(X): return (X-mean) / std
    def restore_func(X): return X * std + mean
    return norm_func, restore_func


def load_csv(data_file, target_name, dem=","):
    df = pd.read_csv(data_file, delimiter=dem)
    return df['smiles'], df[target_name].values


def mse(x, y):
    return ((x-y)**2).mean()


def main(args):
    BSZ, RUNS, LR, N_EPOCH = args.batch_size, args.runs, args.lr, args.epochs
    OUTPUT, SMILES, TARGET = [None]*3
    DATAFILE = Path(args.datafile)
    assert DATAFILE.exists()
    OUTPUT = args.output_dir+DATAFILE.stem+".pkl"
    SMILES, TARGET = load_csv(DATAFILE, "reg", dem=args.delimiter)

    NET = None
    if args.fp_method == FP_METHODS[0]:
        NET = lambda : MLP(hid_dim=FP_LEN, n_class=1)
    elif args.fp_method == FP_METHODS[1]:
        NET = lambda : QSAR(hid_dim=128, n_class=1)

    def build_data_net(args, target):
        if args.fp_method == FP_METHODS[0]:
            #""" CFP """
            data = SmileData(SMILES, target, fp_len=FP_LEN, radius=4)
            net = lambda : MLP(hid_dim=FP_LEN, n_class=1)
            return data, net
        elif args.fp_method == FP_METHODS[1]: 
            #""" NFP """
            net = lambda : QSAR(hid_dim=128, n_class=1)
            data = MolData(SMILES, target)
            return data, net
        else:
            raise NotImplementedError

    res = []
    for _ in range(RUNS):
        train_idx, valid_idx, test_idx = split_train_valid_test(len(TARGET),
                                                                seed=None)
        norm_func, restore_func = normalize_array(
            np.concatenate([TARGET[train_idx], TARGET[valid_idx]], axis=0))
        target = norm_func(TARGET)
        data, net = build_data_net(args, target)
        train_loader = DataLoader(Subset(data, train_idx), batch_size=BSZ,
                                  shuffle=True, drop_last=True)
        valid_loader = DataLoader(Subset(data, valid_idx), batch_size=BSZ,
                                  shuffle=False)
        test_loader = DataLoader(Subset(data, test_idx), batch_size=BSZ,
                                 shuffle=False)
        net = net()
        net = net.fit(train_loader, valid_loader, epochs=N_EPOCH, path=OUTPUT,
                      criterion=nn.MSELoss(), lr=LR)
        score = net.predict(test_loader)
        gt = restore_func(target[test_idx])
        prd = restore_func(score)
        res.append(mse(gt, prd))
        print(f"{DATAFILE.stem}_RUN_{_}: {mse(gt,prd)}")

    avg_mse, std_mse = np.asarray(res).mean(), np.asarray(res).std()
    return avg_mse, std_mse



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("datafile", type=str,
                        help="Specify the input smi filename")
    parser.add_argument("fp_method", default="nfp", type=str,
                        help="Specify the fingerprint method",
                        choices=FP_METHODS)
    parser.add_argument("--delimiter", help="choose the delimiter of the smi\
                        file", type=str, default=" ")
    parser.add_argument("--output_dir", help="specify the output directory",
                        type=str, default="./output/")
    parser.add_argument("-b", "--batch-size", help="batch size",
                        default=64, type=int)
    parser.add_argument("-e", "--epochs", help="number of epochs",
                        default=500, type=int)
    parser.add_argument("-r", "--runs", help="number of runs",
                        default=5, type=int)
    parser.add_argument("-l", "--lr", help="learning rate",
                        default=1e-3, type=float)
    parsed_args = parser.parse_args()
    print("#",parsed_args)
    res = main(parsed_args)
    print(f"{Path(parsed_args.datafile).stem}: {res[0]:.4f}({res[1]:.4f})")
