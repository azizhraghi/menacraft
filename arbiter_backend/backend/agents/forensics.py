"""
ARBITER Forensics Agent
Handles: ELA (Error Level Analysis), FFT frequency fingerprinting, pHash deduplication
"""

import numpy as np
import imagehash
from PIL import Image, ImageChops, ImageEnhance
from scipy.fft import fft2, fftshift
import io
import base64
import os
import json

PHASH_DB_PATH = os.path.join(os.path.dirname(__file__), "../data/phash_db.json")

def _load_phash_db():
    os.makedirs(os.path.dirname(PHASH_DB_PATH), exist_ok=True)
    if os.path.exists(PHASH_DB_PATH):
        with open(PHASH_DB_PATH) as f:
            return json.load(f)
    return {}

def _save_phash_db(db):
    with open(PHASH_DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

def store_phash(claim_id: str, image: Image.Image):
    db = _load_phash_db()
    ph = str(imagehash.phash(image))
    dh = str(imagehash.dhash(image))
    db[claim_id] = {"phash": ph, "dhash": dh}
    _save_phash_db(db)

def check_duplicate(image: Image.Image, current_claim_id: str = None) -> dict:
    db = _load_phash_db()
    ph = imagehash.phash(image)
    dh = imagehash.dhash(image)
    best_match = None
    best_distance = 999

    for cid, hashes in db.items():
        if cid == current_claim_id:
            continue
        try:
            stored_ph = imagehash.hex_to_hash(hashes["phash"])
            stored_dh = imagehash.hex_to_hash(hashes["dhash"])
            ph_dist = ph - stored_ph
            dh_dist = dh - stored_dh
            combined = (ph_dist + dh_dist) / 2
            if combined < best_distance:
                best_distance = combined
                best_match = cid
        except Exception:
            continue

    if best_distance <= 5:
        score = 1.0
        label = "EXACT_DUPLICATE"
    elif best_distance <= 12:
        score = 0.75 - (best_distance - 5) * 0.05
        label = "SIMILAR_IMAGE"
    else:
        score = 0.0
        label = "UNIQUE"

    return {
        "fraud_score": round(score, 3),
        "label": label,
        "matched_claim": best_match if score > 0 else None,
        "hash_distance": int(best_distance),
        "phash": str(ph)
    }


def run_ela(image: Image.Image, quality: int = 90) -> dict:
    img = image.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    ela_img = ImageChops.difference(img, recompressed)
    extrema = ela_img.getextrema()
    max_diff = max([ex[1] for ex in extrema]) or 1
    scale = 255.0 / max_diff
    ela_enhanced = ImageEnhance.Brightness(ela_img).enhance(scale * 10)
    ela_array = np.array(ela_img).astype(float)
    mean_ela = np.mean(ela_array)
    std_ela = np.std(ela_array)
    threshold = mean_ela + 2 * std_ela
    suspicious_pixels = np.sum(ela_array > threshold)
    total_pixels = ela_array.size
    suspicious_ratio = suspicious_pixels / total_pixels
    fraud_score = min(1.0, suspicious_ratio * 8 + (mean_ela / 50))
    ela_heatmap = _array_to_heatmap(ela_array)
    return {
        "fraud_score": round(fraud_score, 3),
        "mean_ela": round(float(mean_ela), 3),
        "std_ela": round(float(std_ela), 3),
        "suspicious_ratio": round(float(suspicious_ratio), 4),
        "label": _score_label(fraud_score),
        "heatmap_b64": ela_heatmap,
        "method": "JPEG Error Level Analysis @ quality=" + str(quality)
    }


def run_fft(image: Image.Image) -> dict:
    gray = np.array(image.convert("L")).astype(float)
    f = fft2(gray)
    fshift = fftshift(f)
    magnitude = np.abs(fshift)
    power = magnitude ** 2
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    low_mask = dist <= max_dist * 0.1
    mid_mask = (dist > max_dist * 0.1) & (dist <= max_dist * 0.4)
    high_mask = dist > max_dist * 0.4
    total_power = np.sum(power) + 1e-10
    low_power = np.sum(power[low_mask]) / total_power
    mid_power = np.sum(power[mid_mask]) / total_power
    high_power = np.sum(power[high_mask]) / total_power
    r_hf = high_power / (low_power + 1e-10)
    if r_hf < 0.0005:
        # Almost zero high-frequency content = heavily smoothed = diffusion model
        fraud_score = 0.85
        generator_type = "DIFFUSION_MODEL"
    elif r_hf > 0.50:
        # Extreme high-frequency artifacts = GAN checkerboard pattern
        fraud_score = 0.80
        generator_type = "GAN_MODEL"
    elif r_hf < 0.002:
        # Suspiciously low but not zero — could be AI upscaled or heavily filtered
        fraud_score = 0.40
        generator_type = "POSSIBLE_AI"
    else:
        # Normal JPEG / camera photo range (0.002 - 0.50)
        fraud_score = max(0, 0.10 - (r_hf - 0.005) * 1.5)
        generator_type = "NATURAL_CAMERA"
    dct_score = _detect_dct_grid(gray)
    if dct_score > 0.85:
        fraud_score = max(fraud_score, dct_score * 0.6)
        generator_type = "GAN_FINGERPRINT_DETECTED"
    log_spectrum = np.log1p(magnitude)
    spectrum_b64 = _array_to_heatmap(log_spectrum)
    return {
        "fraud_score": round(min(fraud_score, 1.0), 3),
        "r_hf": round(float(r_hf), 5),
        "low_power_ratio": round(float(low_power), 4),
        "mid_power_ratio": round(float(mid_power), 4),
        "high_power_ratio": round(float(high_power), 4),
        "dct_grid_score": round(float(dct_score), 3),
        "generator_type": generator_type,
        "label": _score_label(fraud_score),
        "spectrum_b64": spectrum_b64,
        "method": "FFT Frequency Energy Ratio + DCT Grid Detection"
    }


def _detect_dct_grid(gray: np.ndarray) -> float:
    h, w = gray.shape
    h_crop = (h // 8) * 8
    w_crop = (w // 8) * 8
    gray = gray[:h_crop, :w_crop]
    h_diff = np.abs(np.diff(gray, axis=0))
    v_diff = np.abs(np.diff(gray, axis=1))
    h_boundary = np.mean(h_diff[7::8, :]) if h_diff.shape[0] > 8 else 0
    h_non_boundary = np.mean(h_diff) + 1e-10
    v_boundary = np.mean(v_diff[:, 7::8]) if v_diff.shape[1] > 8 else 0
    v_non_boundary = np.mean(v_diff) + 1e-10
    grid_ratio = (h_boundary / h_non_boundary + v_boundary / v_non_boundary) / 2
    return min(1.0, max(0.0, (grid_ratio - 1.0) * 0.5))


def _array_to_heatmap(arr: np.ndarray) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.cm as cm
    arr_2d = arr if arr.ndim == 2 else np.mean(arr, axis=2)
    arr_norm = (arr_2d - arr_2d.min()) / (arr_2d.max() - arr_2d.min() + 1e-10)
    colored = cm.hot(arr_norm)
    img_array = (colored[:, :, :3] * 255).astype(np.uint8)
    img = Image.fromarray(img_array)
    img = img.resize((320, 240), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _score_label(score: float) -> str:
    if score >= 0.75:
        return "HIGH_RISK"
    elif score >= 0.45:
        return "MEDIUM_RISK"
    elif score >= 0.2:
        return "LOW_RISK"
    else:
        return "CLEAN"
