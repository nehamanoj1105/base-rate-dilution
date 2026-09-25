"""
Fast diagnostic script for q non-stationarity (q_orig vs q_inj) and score distribution overlap.
"""

import json
from pathlib import Path
import numpy as np

from src.eval.detector_registry import get_detector
from src.graph_construction.synthetic import generate_synthetic_graph
from src.detection.poisoning_injection import inject_poisoning
from src.attacks.benign_resampler import BenignResampler

def main():
    pool = BenignResampler.create_default_pool(num_graphs=2, edges_per_graph=100500)
    m_grid = [0, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
    seeds = [0, 1]

    detectors = ["graphsage_baseline", "graphsage_inv_features"]

    results = {}

    for det_key in detectors:
        print(f"\n================ Detector: {det_key} ================", flush=True)
        det_data = {
            "q_orig": {},
            "q_inj": {},
            "poison_scores": {},
            "orig_scores": {},
            "inj_scores": {},
            "noise_exceeds_poison_mean_ratio": {},
        }

        for m in m_grid:
            q_orig_list, q_inj_list = [], []
            p_scores_all, o_scores_all, i_scores_all = [], [], []
            exceeds_mean_list = []

            for seed in seeds:
                base_g = generate_synthetic_graph(target_edges=600, seed=seed)
                poison = inject_poisoning(base_g, num_deletions=4, num_insertions=4, num_reorderings=4, num_forgeries=3, seed=seed)
                g_m0 = poison.graph
                gt_ids = set(poison.edge_labels().keys())

                det = get_detector(det_key, seed=seed)
                det.fit_threshold(g_m0, gt_ids)
                thresh = getattr(det, "threshold", 0.5)

                if m > 0:
                    resampler = BenignResampler(pool_graphs=pool, seed=seed + 5000)
                    g_m, injected_ids = resampler.inject_in_place(g_m0, m=m, seed=seed + 5000)
                else:
                    g_m = g_m0
                    injected_ids = set()

                scores = det.score_edges(g_m)

                poison_s = [scores[e] for e in gt_ids if e in scores]
                orig_s = [scores[e] for e in scores if e not in gt_ids and e not in injected_ids]
                inj_s = [scores[e] for e in injected_ids if e in scores]

                n_orig = len(orig_s)
                fp_orig = sum(1 for s in orig_s if s >= thresh)
                q_orig_list.append(fp_orig / n_orig if n_orig > 0 else 0.0)

                if m > 0 and len(inj_s) > 0:
                    fp_inj = sum(1 for s in inj_s if s >= thresh)
                    q_inj_list.append(fp_inj / len(inj_s))

                    if poison_s:
                        mean_p = float(np.mean(poison_s))
                        exceeds_count = sum(1 for s in inj_s if s >= mean_p)
                        exceeds_mean_list.append(exceeds_count / len(inj_s))

                p_scores_all.extend(poison_s)
                o_scores_all.extend(orig_s)
                
                if len(inj_s) > 1000:
                    rng_s = np.random.default_rng(seed)
                    inj_s_sample = list(rng_s.choice(inj_s, size=1000, replace=False))
                else:
                    inj_s_sample = inj_s
                i_scores_all.extend(inj_s_sample)

            q_orig_mean = float(np.mean(q_orig_list))
            q_inj_mean = float(np.mean(q_inj_list)) if q_inj_list else 0.0
            exceeds_mean = float(np.mean(exceeds_mean_list)) if exceeds_mean_list else 0.0

            det_data["q_orig"][str(m)] = q_orig_mean
            det_data["q_inj"][str(m)] = q_inj_mean
            det_data["noise_exceeds_poison_mean_ratio"][str(m)] = exceeds_mean

            det_data["poison_scores"][str(m)] = {
                "mean": round(float(np.mean(p_scores_all)), 6) if p_scores_all else 0.0,
                "std": round(float(np.std(p_scores_all)), 6) if p_scores_all else 0.0,
            }
            det_data["orig_scores"][str(m)] = {
                "mean": round(float(np.mean(o_scores_all)), 6) if o_scores_all else 0.0,
                "std": round(float(np.std(o_scores_all)), 6) if o_scores_all else 0.0,
            }
            det_data["inj_scores"][str(m)] = {
                "mean": round(float(np.mean(i_scores_all)), 6) if i_scores_all else 0.0,
                "std": round(float(np.std(i_scores_all)), 6) if i_scores_all else 0.0,
            }

            p_m = det_data["poison_scores"][str(m)]["mean"]
            p_sd = det_data["poison_scores"][str(m)]["std"]
            i_m = det_data["inj_scores"][str(m)]["mean"]
            i_sd = det_data["inj_scores"][str(m)]["std"]

            print(
                f"[{det_key:<22}] m={m:6d} | q_orig={q_orig_mean:.6f} | q_inj={q_inj_mean:.6f} | "
                f"Poison: {p_m:.4f}+/-{p_sd:.4f} | InjNoise: {i_m:.4f}+/-{i_sd:.4f} | Overlap>=mean(P): {exceeds_mean:.4f}",
                flush=True,
            )

        results[det_key] = det_data

    out_path = Path("results/qq_nonstationarity_and_scores.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved investigation results to {out_path}")

if __name__ == "__main__":
    main()
