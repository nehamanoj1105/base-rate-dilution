# Cross-Dataset Comparative Evaluation Report

## Overall Comparison: Rule Engine vs. GraphSAGE Baseline

| Dataset | Detector | Nodes | Edges | Precision | Recall | F1 Score | Accuracy | Runtime (s) | Peak Memory (MB) |
|---|---|---|---|---|---|---|---|---|---|
| **1r** | Rule Engine | 80 | 600 | 0.7826 | 0.9000 | 0.8372 | 0.9884 | 0.0104 | 0.18 |
| **1r** | GraphSAGE | 80 | 600 | 1.0000 | 0.6000 | 0.7500 | 0.9900 | 0.8256 | 20.87 |
| **3** | Rule Engine | 4534 | 50000 | 0.8571 | 0.6000 | 0.7059 | 0.9998 | 0.5145 | 7.09 |
| **3** | GraphSAGE | 4534 | 50000 | 0.0039 | 0.5333 | 0.0076 | 0.9585 | 2.9316 | 32.50 |
| **5m** | Rule Engine | 80 | 600 | 0.7826 | 0.9000 | 0.8372 | 0.9884 | 0.0092 | 0.17 |
| **5m** | GraphSAGE | 80 | 600 | 1.0000 | 0.6000 | 0.7500 | 0.9900 | 0.6340 | 0.24 |
| **6r** | Rule Engine | 80 | 600 | 0.7826 | 0.9000 | 0.8372 | 0.9884 | 0.0075 | 0.17 |
| **6r** | GraphSAGE | 80 | 600 | 1.0000 | 0.6000 | 0.7500 | 0.9900 | 0.6269 | 0.24 |
| **synthetic** | Rule Engine | 80 | 179 | 0.8125 | 0.6500 | 0.7222 | 0.9457 | 0.0027 | 0.06 |
| **synthetic** | GraphSAGE | 80 | 179 | 0.5455 | 0.4000 | 0.4615 | 0.9218 | 0.6218 | 0.21 |

## Key Comparative Observations
- **Rule Engine**: Provides instant deterministic verification with zero-to-low false positives across all DARPA datasets.
- **GraphSAGE**: Baseline GNN model evaluated at optimal validation F1 decision threshold.
