#!/usr/bin/env bash
# ==============================================================================
# Master One-Command Reproducibility Pipeline for Provenance Tamper Detection
# ==============================================================================
# Usage:
#   ./run_all.sh           # Runs in --quick mode (< 2 mins)
#   ./run_all.sh --quick   # Fast test run with reduced seeds & dilution grid
#   ./run_all.sh --full    # Complete production run (all seeds & full grids)
# ==============================================================================

set -e

MODE="quick"

for arg in "$@"; do
    case $arg in
        --full)
            MODE="full"
            shift
            ;;
        --quick)
            MODE="quick"
            shift
            ;;
    esac
done

export QUICK_MODE=$([ "$MODE" == "quick" ] && echo "1" || echo "0")
PY_ARGS=$([ "$MODE" == "quick" ] && echo "--quick" || echo "")
export PYTHONPATH=.

echo "=============================================================================="
echo " Starting Reproducible Experiment Pipeline (Mode: ${MODE^^})"
echo " Commit: $(git rev-parse HEAD 2>/dev/null || echo 'UNKNOWN')"
echo " Timestamp: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "=============================================================================="

START_TOTAL=$(date +%s)

# Helper function to run a step and print status
run_step() {
    local name="$1"
    local script="$2"
    echo ""
    echo "------------------------------------------------------------------------------"
    echo " [*] Running Step: ${name}"
    echo "     Script: ${script} ${PY_ARGS}"
    echo "------------------------------------------------------------------------------"
    local t0=$(date +%s)
    python3 "${script}" ${PY_ARGS}
    local t1=$(date +%s)
    local dt=$((t1 - t0))
    echo " [+] Step '${name}' completed in ${dt}s."
}

# 1. Noise Realism Audit
run_step "Noise Realism Audit (Phase 1)" "scripts/run_noise_audit.py"

# 2. Gated Model Training & Split Hygiene
run_step "Gated Model Training (Phase 6)" "scripts/run_gated_training.py"

# 3. Baseline Dilution Sweep
run_step "Dilution Sweep (Phases 2-3)" "scripts/run_dilution_sweep.py"

# 3b. Dilution Exponent & AUC Invariance Audit
run_step "Alpha Exponent & AUC Audit (Phase 5)" "scripts/run_alpha_and_auc_audit.py"

# 4. Ablation & Tradeoff Frontier
run_step "Ablation & Tradeoff Sweep (Phase 9 - Experiments E/F)" "scripts/run_ablation_experiments.py"

# 5. Adaptive Attacker Capability Certificates
run_step "Adaptive Attacker Search (Phase 10 - Experiment H)" "scripts/run_adaptive_attacker.py"

# 6. OOD Cross-Scenario & Partition Transfer
run_step "OOD Generalization (Phase 11 - Experiment G)" "scripts/run_ood_experiments.py"

# 7. Second-Domain Elliptic Benchmark
run_step "Second-Domain Generality Benchmark (Phase 12)" "scripts/run_second_domain.py"

# 8. Render Figures & LaTeX Tables
echo ""
echo "------------------------------------------------------------------------------"
echo " [*] Generating Publication Figures & LaTeX Tables..."
echo "------------------------------------------------------------------------------"
python3 scripts/make_figures.py
python3 scripts/make_tables.py

# 9. Generate Results Manifest
echo ""
echo "------------------------------------------------------------------------------"
echo " [*] Generating Results Manifest..."
echo "------------------------------------------------------------------------------"
python3 scripts/generate_manifest.py

END_TOTAL=$(date +%s)
TOTAL_TIME=$((END_TOTAL - START_TOTAL))

echo ""
echo "=============================================================================="
echo " SUCCESS: One-Command Pipeline Executed Cleanly in ${TOTAL_TIME}s"
echo "=============================================================================="
echo " Deliverables Generated:"
echo "   - Manifest:      results/MANIFEST.json"
echo "   - LaTeX Tables:  results/tables/*.tex"
echo "   - Figures:       results/figs/*.png"
echo "=============================================================================="
