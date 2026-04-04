"""
ARBITER Verdict Engine
"""

WEIGHTS = {
    "fft":          0.22,
    "ela":          0.20,
    "phash":        0.18,
    "mahalanobis":  0.15,
    "clip":         0.13,
    "temporal":     0.12,
}

ACTIONS = {
    "REJECT":       (0.70, 1.00),
    "FLAG":         (0.40, 0.70),
    "AUTO_APPROVE": (0.00, 0.40),
}

RISK_LEVELS = {
    "CRITICAL":  (0.85, 1.00),
    "HIGH":      (0.65, 0.85),
    "MEDIUM":    (0.40, 0.65),
    "LOW":       (0.20, 0.40),
    "MINIMAL":   (0.00, 0.20),
}


def compute_verdict(layer_scores: dict, typology: dict, sam_data: dict = None) -> dict:
    weighted_sum = 0.0
    total_weight = 0.0
    breakdown = {}

    for signal, weight in WEIGHTS.items():
        if signal in layer_scores:
            score = layer_scores[signal].get("fraud_score", 0.0)
            weighted_sum += score * weight
            total_weight += weight
            breakdown[signal] = {
                "score": round(score, 3),
                "weight": weight,
                "contribution": round(score * weight, 4),
                "label": layer_scores[signal].get("label", ""),
            }

    risk_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    if layer_scores.get("phash", {}).get("label") == "EXACT_DUPLICATE":
        risk_score = max(risk_score, 0.95)

    gen_type = layer_scores.get("fft", {}).get("generator_type", "")
    if "GAN" in gen_type or "DIFFUSION" in gen_type:
        risk_score = max(risk_score, 0.80)

    exaggeration_flag = None
    if sam_data and sam_data.get("severity_percent") is not None:
        severity_pct = sam_data["severity_percent"]
        exaggeration_flag = {
            "severity_percent": severity_pct,
            "severity_class": sam_data.get("severity_class"),
            "note": f"Physical damage covers {severity_pct:.1f}% of vehicle surface"
        }

    risk_score = round(min(1.0, max(0.0, risk_score)), 3)

    action = "AUTO_APPROVE"
    for act, (low, high) in ACTIONS.items():
        if low <= risk_score < high:
            action = act
            break
    if risk_score >= 0.70:
        action = "REJECT"

    risk_level = "MINIMAL"
    for level, (low, high) in RISK_LEVELS.items():
        if low <= risk_score <= high:
            risk_level = level
            break

    ruling = _generate_ruling(risk_score, action, typology, breakdown)

    return {
        "risk_score": risk_score,
        "risk_score_percent": int(risk_score * 100),
        "action": action,
        "risk_level": risk_level,
        "fraud_type": typology.get("primary_type", "UNKNOWN"),
        "fraud_type_description": typology.get("type_description", ""),
        "ruling": ruling,
        "breakdown": breakdown,
        "exaggeration_check": exaggeration_flag,
        "confidence": _compute_confidence(breakdown),
        "methodology": "Weighted ensemble — ELA(20%) + FFT(22%) + pHash(18%) + DINOv2(15%) + CLIP(13%) + Temporal(12%)"
    }


def _generate_ruling(score: float, action: str, typology: dict, breakdown: dict) -> str:
    fraud_type = typology.get("primary_type", "UNKNOWN")
    top_signal = max(breakdown.items(), key=lambda x: x[1]["score"]) if breakdown else None

    if action == "REJECT":
        if fraud_type == "GEN_AI":
            return f"AI-generated image detected with {int(score*100)}% confidence — claim must be rejected."
        elif fraud_type == "RECYCLED_CLAIM":
            return f"Duplicate image matched to existing claim — evidence of claim recycling fraud."
        elif fraud_type == "SPLICE_FRAUD":
            return f"Digital manipulation detected in {int(score*100)}% of forensic signals — rejection recommended."
        else:
            return f"Multiple forensic signals ({int(score*100)}% combined risk) indicate fraudulent submission."
    elif action == "FLAG":
        signal_name = top_signal[0].upper() if top_signal else "FORENSIC"
        return f"{signal_name} anomaly score of {top_signal[1]['score']:.2f} warrants manual review by claims adjuster."
    else:
        return f"Forensic analysis found no significant indicators of manipulation — claim cleared for processing."


def _compute_confidence(breakdown: dict) -> float:
    if not breakdown:
        return 0.5
    scores = [v["score"] for v in breakdown.values()]
    import numpy as np
    variance = float(np.var(scores))
    confidence = max(0.5, 1.0 - variance * 2)
    return round(confidence, 3)


def get_action_color(action: str) -> str:
    return {"REJECT": "#ef4444", "FLAG": "#f59e0b", "AUTO_APPROVE": "#10b981"}.get(action, "#6b7280")
