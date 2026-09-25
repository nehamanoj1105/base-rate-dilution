"""
Second-Domain Benchmark Evaluation Module (Phase 12).

Reproduces base-rate dilution (precision decay & AUC invariance) on the public
Elliptic Bitcoin Graph Anomaly Benchmark.

Scientific Goal:
  Demonstrate that precision decay under dilution (alpha_hat ~ 1.0) and AUC invariance
  is a general property of GNN anomaly detection, not unique to OS provenance graphs.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import scipy.stats as stats
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import precision_recall_curve, roc_auc_score
from torch_geometric.datasets import EllipticBitcoinDataset
from torch_geometric.nn import SAGEConv

from src.eval.alpha_estimator import AlphaFitResult, fit_alpha_exponent
from src.ml.utils import get_device, set_seed


class EllipticGraphSAGE(nn.Module):
    """Standard 2-layer GraphSAGE baseline model for node anomaly detection on Elliptic."""

    def __init__(self, in_channels: int = 165, hidden_channels: int = 64):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.classifier = nn.Linear(hidden_channels, 1)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.conv1(x, edge_index))
        h = F.relu(self.conv2(h, edge_index))
        logits = self.classifier(h).squeeze(-1)
        return logits


def train_elliptic_model(
    x: torch.Tensor,
    edge_index: torch.Tensor,
    y: torch.Tensor,
    train_mask: torch.Tensor,
    val_mask: torch.Tensor,
    epochs: int = 25,
    lr: float = 0.01,
    hidden_channels: int = 64,
    seed: int = 42,
) -> tuple[EllipticGraphSAGE, float]:
    """
    Trains GraphSAGE on Elliptic training nodes and calibrates threshold on val set at m=0.
    """
    set_seed(seed)
    device = get_device()

    model = EllipticGraphSAGE(in_channels=x.size(-1), hidden_channels=hidden_channels).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    
    # Class weighting to handle rare positive class (Class 1)
    pos_weight = torch.tensor([5.0], device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    x_dev = x.to(device)
    edge_idx_dev = edge_index.to(device)
    y_dev = y.to(device)
    train_mask_dev = train_mask.to(device)
    val_mask_dev = val_mask.to(device)

    # Filter out unlabeled nodes (y == 2) for training loss
    train_eval_mask = train_mask_dev & (y_dev != 2)
    val_eval_mask = val_mask_dev & (y_dev != 2)

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        logits = model(x_dev, edge_idx_dev)
        loss = criterion(logits[train_eval_mask], y_dev[train_eval_mask].float())
        loss.backward()
        optimizer.step()

    # Calibrate threshold on Val set at m=0 for max F1
    model.eval()
    with torch.no_grad():
        val_logits = model(x_dev, edge_idx_dev)[val_eval_mask]
        val_probs = torch.sigmoid(val_logits).cpu().numpy()
        val_y = y_dev[val_eval_mask].cpu().numpy().astype(int)

    precisions, recalls, thresholds = precision_recall_curve(val_y, val_probs)
    f1_scores = np.where(
        (precisions + recalls) > 0,
        2 * (precisions * recalls) / (precisions + recalls),
        0.0,
    )
    best_idx = np.argmax(f1_scores)
    best_threshold = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5

    return model, best_threshold


def evaluate_second_domain_dilution(
    m_grid: Sequence[int] = (0, 1000, 5000, 10000, 20000, 50000, 100000),
    seeds: Sequence[int] = (0, 1, 2, 3, 4),
    root_dir: str = "data/elliptic",
    output_json_path: Path | str = "results/second_domain.json",
) -> dict[str, Any]:
    """
    Executes Phase 12 Second-Domain Dilution evaluation on Elliptic.
    """
    print("[*] Loading Elliptic Bitcoin Dataset...")
    dataset = EllipticBitcoinDataset(root=root_dir)
    data = dataset[0]

    num_nodes = data.x.size(0)
    y = data.y  # 0: licit, 1: illicit, 2: unknown

    # Identify labelled nodes
    labelled_indices = (y != 2).nonzero(as_tuple=True)[0]
    unlabelled_indices = (y == 2).nonzero(as_tuple=True)[0]

    sweep_records: list[dict[str, Any]] = []

    for seed in seeds:
        print(f"[*] Running Elliptic Dilution Evaluation for Seed {seed}...")
        set_seed(seed)

        # Shuffle labelled nodes for train/val/test splits
        rng = np.random.default_rng(seed)
        shuffled = rng.permutation(labelled_indices.numpy())

        n_lab = len(shuffled)
        n_train = int(0.6 * n_lab)
        n_val = int(0.2 * n_lab)

        train_nodes = set(shuffled[:n_train])
        val_nodes = set(shuffled[n_train:n_train + n_val])
        test_nodes = set(shuffled[n_train + n_val:])

        train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        val_mask = torch.zeros(num_nodes, dtype=torch.bool)
        test_mask = torch.zeros(num_nodes, dtype=torch.bool)

        for idx in train_nodes:
            train_mask[idx] = True
        for idx in val_nodes:
            val_mask[idx] = True
        for idx in test_nodes:
            test_mask[idx] = True

        # Load frozen threshold from config/frozen_thresholds.json
        frozen_thresh = 0.8289
        thresh_path = Path("config/frozen_thresholds.json")
        if thresh_path.exists():
            with open(thresh_path, "r", encoding="utf-8") as tf:
                tdata = json.load(tf)
                frozen_thresh = tdata.get("thresholds", {}).get("elliptic_gnn", 0.8289)

        # Train model for current seed
        model, _ = train_elliptic_model(
            data.x, data.edge_index, y, train_mask, val_mask, epochs=25, seed=seed
        )
        operating_thresh = frozen_thresh

        device = get_device()
        model.eval()

        # Reserve unlabelled/licit nodes as dilution noise pool
        dilution_pool = unlabelled_indices.numpy()

        for m in m_grid:
            # Construct evaluation graph by injecting m dilution nodes/edges
            if m == 0:
                eval_test_mask = test_mask.clone()
                eval_x = data.x
                eval_edge_idx = data.edge_index
                eval_y = y
            else:
                # Sample m noise nodes from dilution pool
                sampled_noise_nodes = rng.choice(
                    dilution_pool, size=min(m, len(dilution_pool)), replace=False
                )
                noise_node_set = set(sampled_noise_nodes)

                # Keep test nodes + sampled noise nodes
                eval_nodes = list(set(test_nodes).union(noise_node_set))
                node_map = {orig: new for new, orig in enumerate(eval_nodes)}

                eval_x = data.x[eval_nodes]
                eval_y = y[eval_nodes].clone()
                # Set label of injected noise nodes (unlabelled) to 0 (Licit/Negative)
                for orig_idx in noise_node_set:
                    new_idx = node_map[orig_idx]
                    eval_y[new_idx] = 0

                # Filter edge index to active nodes
                src = data.edge_index[0].numpy()
                tgt = data.edge_index[1].numpy()

                mask = np.vectorize(lambda n: n in node_map)
                edge_mask = mask(src) & mask(tgt)

                new_src = [node_map[s] for s in src[edge_mask]]
                new_tgt = [node_map[t] for t in tgt[edge_mask]]

                eval_edge_idx = torch.tensor([new_src, new_tgt], dtype=torch.long)
                eval_test_mask = torch.ones(len(eval_nodes), dtype=torch.bool)

            # Score evaluation nodes
            with torch.no_grad():
                x_dev = eval_x.to(device)
                edge_dev = eval_edge_idx.to(device)
                eval_logits = model(x_dev, edge_dev)
                eval_probs = torch.sigmoid(eval_logits).cpu().numpy()

            # Filter to test set evaluation nodes
            eval_mask_np = eval_test_mask.numpy()
            test_probs = eval_probs[eval_mask_np]
            test_y = eval_y.numpy()[eval_mask_np].astype(int)

            if len(test_y) == 0 or np.sum(test_y) == 0:
                continue

            # Classifications with frozen operating threshold
            preds = (test_probs >= operating_thresh).astype(int)
            tp = int(np.sum((preds == 1) & (test_y == 1)))
            fp = int(np.sum((preds == 1) & (test_y == 0)))
            fn = int(np.sum((preds == 0) & (test_y == 1)))
            tn = int(np.sum((preds == 0) & (test_y == 0)))

            precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2.0 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            try:
                auc = float(roc_auc_score(test_y, test_probs))
            except Exception:
                auc = 0.5

            # Calculate node degrees for score locality Spearman rho
            degrees = np.bincount(eval_edge_idx[0].numpy(), minlength=len(eval_x))
            test_degrees = degrees[eval_mask_np]

            if len(test_degrees) > 1 and np.std(test_degrees) > 0 and np.std(test_probs) > 0:
                rho, _ = stats.spearmanr(test_degrees, test_probs)
                rho_val = float(rho) if not np.isnan(rho) else 0.0
            else:
                rho_val = 0.0

            sweep_records.append({
                "seed": seed,
                "m": m,
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "f1": round(f1, 6),
                "auc": round(auc, 6),
                "spearman_rho": round(rho_val, 6),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "operating_threshold": round(operating_thresh, 4),
            })

    # Fit dilution exponent alpha_hat across m > 0
    m_vals = [r["m"] for r in sweep_records]
    precs = [r["precision"] for r in sweep_records]
    seeds_list = [r["seed"] for r in sweep_records]

    alpha_fit = fit_alpha_exponent(m_vals=m_vals, precisions=precs, seeds=seeds_list)

    out_data = {
        "dataset": "EllipticBitcoinDataset",
        "m_grid": list(m_grid),
        "seeds": list(seeds),
        "alpha_fit": alpha_fit.to_dict(),
        "sweep_records": sweep_records,
    }

    out_p = Path(output_json_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"[+] Elliptic Second-Domain Evaluation Complete! Output saved to {output_json_path}")
    return out_data
