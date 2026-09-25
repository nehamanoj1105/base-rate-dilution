# Causal Provenance Graph Tamper Detection Framework

A framework for validating causal consistency and detecting provenance
graph tampering on DARPA Transparent Computing Engagement 3 datasets and
synthetic provenance graphs using deterministic semantic rules and a
GraphSAGE baseline.

## Overview

Modern provenance-based intrusion detection systems (PIDS) assume that
collected system provenance graphs are trustworthy. This project
investigates whether the provenance graph itself has been tampered with.

The framework evaluates detection resilience against post-collection
provenance attacks:

-   Edge Deletion: erasing causal log events
-   Edge Insertion: fabricating unperformed system actions
-   Edge Reordering: shifting event timestamps out of true causal order
-   Dependency Forgery: re-attributing actions to different actors
-   Adversarial Mimicry: camouflaging poisoning within statistical
    background noise

## Repository Structure

``` text
src/
├── graph_construction/
│   ├── schema.py         # ProvenanceGraph, ProvenanceNode, ProvenanceEdge data model
│   ├── cdm_parser.py     # Parser interfaces
│   ├── graph_loader.py   # Data loader for parsed DARPA CSV scenarios
│   ├── converter.py      # DataFrame to ProvenanceGraph schema converter
│   └── synthetic.py      # Synthetic provenance graph generator
│
├── detection/
│   ├── poisoning_injection.py  # Random and targeted poisoning attack suite
│   ├── mimicry_attack.py       # Adversarial mimicry attack generator
│   ├── rule_engine.py          # 15 deterministic semantic validation rules
│   └── rule_based.py           # Rule engine entrypoints
│
├── ml/
│   ├── dataset.py        # ProvenanceGraph to PyTorch Geometric Data converter
│   ├── graphsage.py      # 2-layer GraphSAGE architecture and edge predictor
│   ├── train.py          # FocalLoss, weighted BCE training and threshold search
│   ├── predict.py        # Edge and node tamper prediction
│   ├── metrics.py        # ROC, PR curves, threshold sweep and calibration stats
│   └── utils.py          # PyTorch device and random seed management
│
├── eval/
│   ├── metrics.py        # Evaluation metrics
│   ├── confusion_matrix.py # Confusion matrix calculations
│   ├── evaluator.py      # Ground-truth comparison engine
│   ├── report.py         # CSV and Markdown report generators
│   ├── cross_dataset.py  # Cross-scenario evaluation across DARPA datasets
│   ├── scalability.py    # Runtime, memory and throughput benchmarking
│   ├── ablation.py       # Rule ablation study and per-rule statistics
│   └── robustness.py     # Adversarial mimicry robustness evaluation
│
scripts/
├── run_evaluation.py     # Executes multi-seed rule engine evaluation
├── run_graphsage.py      # Trains GraphSAGE and generates ROC/PR curves
├── run_cross_dataset.py  # Executes cross-scenario evaluation
├── run_scalability.py    # Runs scalability, memory and throughput benchmarks
└── run_mimicry.py        # Evaluates detector robustness under mimicry attacks

tests/                    # 103 unit tests covering all components
results/                  # Generated CSV reports, Markdown summary tables and plots
```

## Implementation Status

### Implemented

-   Provenance Graph Data Model: Node types include `process`, `file`,
    `user`, and `network`. Edge types include `read`, `write`,
    `execute`, `connect`, `spawn`, and `delete`.
-   DARPA Scenario Support: Pre-parsed DARPA TC E3 scenarios `1r`, `3`,
    `5m`, and `6r` are loaded through
    `src/graph_construction/graph_loader.py`.
-   Synthetic Graph Generator: Parametric provenance graph generation
    through `src/graph_construction/synthetic.py`.
-   Poisoning Attack Suite: Four random attack vectors and four targeted
    attack vectors through `src/detection/poisoning_injection.py`.
-   Adversarial Mimicry Generator: Camouflage noise injection designed
    to preserve degree, type, and timestamp distributions.
-   Semantic Rule Engine: 15 deterministic semantic rules through
    `src/detection/rule_engine.py`.
-   Evaluation Framework: 13 evaluation metrics including Precision,
    Recall, F1, Accuracy, Specificity, FPR, FNR, Balanced Accuracy, MCC,
    AP, ROC-AUC, and PR-AUC.
-   GraphSAGE Baseline: PyTorch Geometric implementation with
    class-imbalance loss weighting and threshold optimization.
-   Scalability Benchmarking: Runtime, RSS/peak memory, and throughput
    profiling up to 1,000,000 edges.
-   Rule Ablation and Statistics: Category removal, leave-one-out
    ablation, and per-rule violation tracking.
-   Detector Robustness Benchmarking: Rule Engine and GraphSAGE
    evaluation under `none`, `light`, `medium`, and `heavy` mimicry
    strengths.
-   Multi-Scenario Evaluation: Automated evaluation across DARPA
    datasets `1r`, `3`, `5m`, `6r`, and synthetic graphs.
-   Unit Test Suite: 103 unit tests passing through `pytest`.

### In Progress

-   Fine-grained microsecond temporal sequence window tuning for online
    provenance log streams.

### Future Work

-   Direct binary Common Data Model (`.bin`) raw log stream ingestion.
-   Joint hybrid inference combining GNN embeddings with deterministic
    rule violation constraints.

## Implemented Semantic Rules

The Semantic Rule Engine implements 15 rules covering structural,
temporal, and semantic invariants.

  --------------------------------------------------------------------------------------
  \#                Rule Class Name                 Category          Primary Invariant
                                                                      Checked
  ----------------- ------------------------------- ----------------- ------------------
  1                 `DuplicateEdgeRule`             Structural        Identifies
                                                                      duplicate edge
                                                                      tuples

  2                 `DuplicateEventRule`            Structural        Identifies
                                                                      duplicate event
                                                                      IDs

  3                 `SpawnConsistencyRule`          Semantic          Validates `SPAWN`
                                                                      edges target
                                                                      `process` nodes

  4                 `ExecutionConsistencyRule`      Semantic          Validates
                                                                      `EXECUTE` edges
                                                                      target `file`
                                                                      nodes

  5                 `ReadWriteConsistencyRule`      Semantic          Validates `READ`
                                                                      and `WRITE` edges
                                                                      target `file`
                                                                      nodes

  6                 `NetworkConsistencyRule`        Semantic          Validates
                                                                      `CONNECT` edges
                                                                      target `network`
                                                                      endpoints

  7                 `DeleteConsistencyRule`         Semantic          Validates `DELETE`
                                                                      edges target
                                                                      `file` nodes

  8                 `SelfLoopRule`                  Structural        Flags invalid
                                                                      self-referential
                                                                      edges

  9                 `MissingNodeRule`               Structural        Flags edges
                                                                      referencing
                                                                      non-existent nodes

  10                `TimestampRule`                 Temporal          Validates
                                                                      non-negative Unix
                                                                      epoch timestamps

  11                `UnspawnedProcessRule`          Structural        Detects active
                                                                      processes missing
                                                                      parent `SPAWN`
                                                                      edges

  12                `SequenceGapRule`               Structural        Identifies missing
                                                                      event sequence
                                                                      indices

  13                `ParentChildTemporalRule`       Temporal          Ensures child
                                                                      spawn timestamp
                                                                      follows parent
                                                                      spawn

  14                `ProcessActivityTemporalRule`   Temporal          Ensures process
                                                                      activity follows
                                                                      process spawn

  15                `SequenceMonotonicityRule`      Temporal          Detects timestamp
                                                                      inversions in
                                                                      process streams
  --------------------------------------------------------------------------------------

## One-Command Reproducibility Pipeline

Every experimental result, figure, and LaTeX table in the paper can be reproduced end-to-end with a single command.

### Installation & Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt
```

### Execution Modes & Expected Runtimes

```bash
# 1. Quick Mode (Fast end-to-end verification, ~1-2 minutes)
./run_all.sh --quick

# 2. Full Mode (Complete paper reproduction with 5 seeds and full dilution grids, ~15-30 minutes)
./run_all.sh --full
```

### Reproducibility Pipeline & Generated Artifacts

Executing `./run_all.sh` runs all seven paper experiments in dependency order, renders publication figures and LaTeX tables, and updates the provenance manifest:

1. **Noise Realism Audit**: `scripts/run_noise_audit.py` $\rightarrow$ `results/noise_realism_audit.json`
2. **Gated Model Training & Split Hygiene**: `scripts/run_gated_training.py` $\rightarrow$ `results/training_metrics.json`
3. **Dilution Sweep Harness**: `scripts/run_dilution_sweep.py` $\rightarrow$ `results/dilution_sweep.csv`
4. **Detector Ablation & Tradeoff Frontier**: `scripts/run_ablation_experiments.py` $\rightarrow$ `results/ablation_experiments.json`
5. **Adaptive Attacker Certificates**: `scripts/run_adaptive_attacker.py` $\rightarrow$ `results/adaptive_attacker.json`
6. **OOD Generalization & Partition Transfer**: `scripts/run_ood_experiments.py` $\rightarrow$ `results/ood_experiments.json`
7. **Second-Domain Elliptic Benchmark**: `scripts/run_second_domain.py` $\rightarrow$ `results/second_domain.json`
8. **Figure & LaTeX Table Generators**: `scripts/make_figures.py` and `scripts/make_tables.py` $\rightarrow$ `results/figs/*.png`, `results/tables/*.tex`
9. **Results Manifest**: `scripts/generate_manifest.py` $\rightarrow$ `results/MANIFEST.json`

> [!NOTE]
> Every number appearing in the generated LaTeX tables in `results/tables/` traces directly to an execution output JSON file listed in `results/MANIFEST.json`. Zero numbers in the paper tables are typed by hand.

## Execution Instructions

### 1. Run Unit Tests

``` bash
python3 -m pytest -q
```

### 2. Run Semantic Rule Engine Evaluation

``` bash
python3 scripts/run_evaluation.py
```

### 3. Run GraphSAGE Training and Threshold Evaluation

``` bash
python3 scripts/run_graphsage.py --epochs 30 --seed 42
```

### 4. Run Multi-Scenario DARPA Evaluation

``` bash
python3 scripts/run_cross_dataset.py
```

### 5. Run Scalability and Throughput Benchmarking

``` bash
python3 scripts/run_scalability.py
```

### 6. Run Adversarial Mimicry Evaluation

``` bash
python3 scripts/run_mimicry.py
```

## Dataset and Evaluation Architecture

The framework supports three data ingestion and evaluation modes.

### 1. Synthetic Evaluation

Fast and reproducible evaluation on parametrically generated synthetic
provenance graphs.

Source:

`src/graph_construction/synthetic.py`

### 2. Parsed DARPA CSV Evaluation

The primary benchmark mode uses pre-parsed node and edge CSV tables from
DARPA TC E3 scenarios:

-   `1r`: TRACE
-   `3`: CADETS
-   `5m`: ClearScope
-   `6r`: THEIA

Source:

`src/graph_construction/graph_loader.py`

### 3. Raw CDM Parser

Parser interfaces for raw binary Common Data Model (`.bin`) stream files
are available through:

`src/graph_construction/cdm_parser.py`

Raw binary ingestion is not part of the reported evaluation execution
scripts.

## Current Framework Limitations

### 1. Evaluation Data Source

Reported benchmarks execute on pre-parsed DARPA TC E3 CSV tables under
`data/parsed/` and on synthetic graphs.

The raw binary CDM (`.bin`) parsing interface exists in
`src/graph_construction/cdm_parser.py`, but it is not invoked by the
standard evaluation scripts.

### 2. GraphSAGE Precision Under Heavy Mimicry Noise

GraphSAGE aggregates features over two-hop neighborhoods. Under heavy
mimicry camouflage with approximately 150% additional noise edges, node
representations become less discriminative because the injected edges
resemble normal process interactions. This results in reduced precision.

### 3. Subgraph Slicing for Benchmarks

Evaluation across multiple DARPA TC E3 scenarios uses subgraph slices of
up to 50,000 edges to maintain reproducible execution times.
