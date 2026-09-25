# Adversarial Mimicry Attack Robustness Report

## Performance Under Increasing Mimicry Strength

| Strength | Detector | Total Edges | Noise Edges | Poison Edges | Precision | Recall | F1 Score | Accuracy | ROC-AUC | PR-AUC | Runtime (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **NONE** | Rule Engine | 234 | 0 | 20 | 0.8750 | 0.7000 | 0.7778 | 0.9665 | 1.0000 | 0.6125 | 0.0013 |
| **NONE** | GraphSAGE | 234 | 0 | 20 | 0.5833 | 0.4667 | 0.5185 | 0.9444 | 0.8551 | 0.5297 | 0.0007 |
| **LIGHT** | Rule Engine | 466 | 232 | 20 | 0.8750 | 0.7000 | 0.7778 | 0.9830 | 1.0000 | 0.6125 | 0.0023 |
| **LIGHT** | GraphSAGE | 466 | 232 | 20 | 0.1628 | 0.4667 | 0.2414 | 0.9056 | 0.7956 | 0.3256 | 0.0009 |
| **MEDIUM** | Rule Engine | 708 | 474 | 20 | 0.8750 | 0.7000 | 0.7778 | 0.9888 | 1.0000 | 0.6125 | 0.0036 |
| **MEDIUM** | GraphSAGE | 708 | 474 | 20 | 0.0833 | 0.6000 | 0.1463 | 0.8517 | 0.7715 | 0.2690 | 0.0010 |
| **HEAVY** | Rule Engine | 1,199 | 965 | 20 | 0.8750 | 0.7000 | 0.7778 | 0.9934 | 1.0000 | 0.6125 | 0.0050 |
| **HEAVY** | GraphSAGE | 1,199 | 965 | 20 | 0.0452 | 0.6000 | 0.0841 | 0.8365 | 0.7541 | 0.2379 | 0.0013 |

## Detector Comparison: Original vs. Camouflaged Mimicry

| Detector | No Mimicry F1 | Light Mimicry F1 | Medium Mimicry F1 | Heavy Mimicry F1 | Impact Assessment |
|---|---|---|---|---|---|
| **Rule Engine** | 0.7778 | 0.7778 | 0.7778 | 0.7778 | Highly Robust (Deterministic Causal Rules) |
| **GraphSAGE** | 0.5185 | 0.2414 | 0.1463 | 0.0841 | Sensitive to Noise Camouflage |
