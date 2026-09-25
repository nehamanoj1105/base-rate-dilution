"""
Dilution Exponent (Alpha) Estimator and Theoretical Precision Module.

Estimates dilution exponent alpha_hat and confidence intervals from empirical precision decay curves,
and computes theoretical precision predictions under base-rate dilution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Sequence

import numpy as np
from scipy.optimize import curve_fit


@dataclass
class AlphaFitResult:
    """Dataclass holding dilution exponent fit parameters and confidence bounds."""

    alpha_hat: float
    ci_lower: float
    ci_upper: float
    r_squared: Optional[float]
    intercept: float
    fitted_m_min: int
    fitted_m_max: int
    n_samples: int

    def to_dict(self) -> dict[str, Any]:
        """Convert fit result to JSON serializable dictionary."""
        return {
            "alpha_hat": round(self.alpha_hat, 6),
            "ci_lower": round(self.ci_lower, 6),
            "ci_upper": round(self.ci_upper, 6),
            "r_squared": round(self.r_squared, 6) if self.r_squared is not None else None,
            "intercept": round(self.intercept, 6),
            "fitted_m_min": self.fitted_m_min,
            "fitted_m_max": self.fitted_m_max,
            "n_samples": self.n_samples,
        }


def theoretical_precision_prediction(
    p: float, q: float, k: int, n: int, m: float | Sequence[float]
) -> np.ndarray | float:
    """
    Computes theoretical precision under base-rate dilution:
    Precision(m) = (p * k) / (p * k + q * (n + m))

    where p is TPR, q is FPR, k is poison edge count, n is base benign edge count, and m is dilution volume.
    """
    m_arr = np.array(m, dtype=float)
    numerator = p * k
    denominator = numerator + q * (n + m_arr)

    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(denominator > 0, numerator / denominator, 1.0)

    if np.ndim(m) == 0:
        return float(prec)
    return prec


def fit_alpha_exponent(
    m_vals: Sequence[float],
    precisions: Sequence[float],
    seeds: Optional[Sequence[int]] = None,
    total_edges: Optional[Sequence[float]] = None,
    m0: float = 0.0,
    n_bootstrap: int = 500,
    ci_level: float = 0.95,
) -> AlphaFitResult:
    """
    Fits the dilution exponent alpha_hat in the model:
    Precision(m) = Precision(0) / (1 + (m / N_0))^alpha

    where N_0 is the base graph size.
    Returns AlphaFitResult with bootstrap confidence intervals.
    """
    m_arr = np.array(m_vals, dtype=float)
    p_arr = np.array(precisions, dtype=float)

    # Filter m > 0 for log-log regression fitting
    mask = m_arr > 0
    if not np.any(mask):
        return AlphaFitResult(
            alpha_hat=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            r_squared=1.0,
            intercept=0.0,
            fitted_m_min=0,
            fitted_m_max=0,
            n_samples=len(m_vals),
        )

    m_fit = m_arr[mask]
    p_fit = p_arr[mask]

    p0 = float(np.mean(p_arr[m_arr == 0])) if np.any(m_arr == 0) else float(p_fit[0])
    p0 = max(p0, 1e-6)

    # If precision is constant across all m, alpha_hat = 0.0
    if np.max(p_fit) - np.min(p_fit) < 1e-6 or np.all(p_fit >= p0 - 1e-6):
        return AlphaFitResult(
            alpha_hat=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            r_squared=1.0,
            intercept=0.0,
            fitted_m_min=int(np.min(m_fit)),
            fitted_m_max=int(np.max(m_fit)),
            n_samples=len(m_fit),
        )

    # Reference scale N_0
    N0 = float(np.mean(total_edges)) if total_edges is not None else 1000.0

    # Fit alpha using log transform: y = log(p0 / p(m) - 1) = alpha * log(m / N0) + c
    # Or linear log-log decay model: log(p(m) / p0) = -alpha * log(1 + m / N0)
    x = np.log(1.0 + m_fit / N0)
    # Apply floor to p_fit to avoid log(0)
    eps = 1.0 / (N0 + np.max(m_fit))
    p_floored = np.maximum(p_fit, eps)
    y = np.log(p_floored / p0)

    # OLS regression
    def fit_single(x_data, y_data):
        if len(x_data) < 2:
            return 0.0, 0.0, 0.0
        # Slope = -alpha -> alpha = -slope
        poly = np.polyfit(x_data, y_data, 1)
        slope, intercept = poly[0], poly[1]
        alpha = -slope
        # Calculate R^2
        y_pred = poly[0] * x_data + poly[1]
        ss_res = np.sum((y_data - y_pred) ** 2)
        ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 1.0
        return float(alpha), float(intercept), float(r2)

    alpha_hat, intercept, r2 = fit_single(x, y)

    # Bootstrap for CI
    alphas = []
    rng = np.random.default_rng(42)
    n_pts = len(x)

    if seeds is not None and len(set(seeds)) > 1:
        unique_seeds = np.array(list(set(seeds)))
        seeds_arr = np.array(seeds)[mask]
        for _ in range(n_bootstrap):
            sampled_seeds = rng.choice(unique_seeds, size=len(unique_seeds), replace=True)
            idx_list = []
            for s in sampled_seeds:
                idx_list.extend(np.where(seeds_arr == s)[0])
            if len(idx_list) > 1:
                a_b, _, _ = fit_single(x[idx_list], y[idx_list])
                alphas.append(a_b)
    else:
        for _ in range(n_bootstrap):
            idx = rng.choice(n_pts, size=n_pts, replace=True)
            a_b, _, _ = fit_single(x[idx], y[idx])
            alphas.append(a_b)

    if alphas:
        alpha_lower = float(np.percentile(alphas, (1 - ci_level) / 2 * 100))
        alpha_upper = float(np.percentile(alphas, (1 + ci_level) / 2 * 100))
    else:
        alpha_lower = alpha_hat
        alpha_upper = alpha_hat

    return AlphaFitResult(
        alpha_hat=alpha_hat,
        ci_lower=alpha_lower,
        ci_upper=alpha_upper,
        r_squared=r2,
        intercept=intercept,
        fitted_m_min=int(np.min(m_fit)),
        fitted_m_max=int(np.max(m_fit)),
        n_samples=len(m_fit),
    )
