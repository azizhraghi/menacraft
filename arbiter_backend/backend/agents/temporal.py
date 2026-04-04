"""
ARBITER Temporal & Geospatial Forensics Agent
"""

import io
from datetime import datetime
from PIL import Image
import piexif
import base64


def run_temporal_analysis(image: Image.Image, claim_date: str = None,
                           claim_location: str = None) -> dict:
    exif_data = _extract_exif(image)
    timestamp_result = _analyze_timestamp(exif_data, claim_date)
    gps_result = _analyze_gps(exif_data, claim_location)
    metadata_result = _analyze_metadata_integrity(exif_data, image)

    scores = [timestamp_result["fraud_score"],
              gps_result["fraud_score"],
              metadata_result["fraud_score"]]
    combined_score = max(scores) * 0.6 + sum(scores) / len(scores) * 0.4

    flags = []
    if timestamp_result["fraud_score"] > 0.4:
        flags.append(timestamp_result.get("flag", "Timestamp anomaly"))
    if gps_result["fraud_score"] > 0.4:
        flags.append(gps_result.get("flag", "GPS anomaly"))
    if metadata_result["fraud_score"] > 0.4:
        flags.append(metadata_result.get("flag", "Metadata stripped"))

    return {
        "fraud_score": round(min(combined_score, 1.0), 3),
        "label": _score_label(combined_score),
        "flags": flags,
        "timestamp": timestamp_result,
        "gps": gps_result,
        "metadata_integrity": metadata_result,
        "raw_exif_summary": _summarize_exif(exif_data),
        "method": "EXIF DateTimeOriginal + GPS + Metadata integrity analysis"
    }


def _extract_exif(image: Image.Image) -> dict:
    result = {
        "datetime_original": None,
        "datetime_digitized": None,
        "gps_lat": None,
        "gps_lon": None,
        "make": None,
        "model": None,
        "software": None,
        "has_exif": False,
        "has_gps": False,
    }
    try:
        exif_bytes = image.info.get("exif", b"")
        if not exif_bytes:
            return result
        exif_dict = piexif.load(exif_bytes)
        result["has_exif"] = True
        exif_ifd = exif_dict.get("Exif", {})
        dt_orig = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
        if dt_orig:
            result["datetime_original"] = dt_orig.decode() if isinstance(dt_orig, bytes) else str(dt_orig)
        ifd0 = exif_dict.get("0th", {})
        make = ifd0.get(piexif.ImageIFD.Make)
        model = ifd0.get(piexif.ImageIFD.Model)
        software = ifd0.get(piexif.ImageIFD.Software)
        result["make"] = make.decode().strip('\x00') if isinstance(make, bytes) else str(make) if make else None
        result["model"] = model.decode().strip('\x00') if isinstance(model, bytes) else str(model) if model else None
        result["software"] = software.decode().strip('\x00') if isinstance(software, bytes) else str(software) if software else None
        gps_ifd = exif_dict.get("GPS", {})
        if gps_ifd:
            result["has_gps"] = True
            lat = _convert_gps(gps_ifd.get(piexif.GPSIFD.GPSLatitude),
                               gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b'N'))
            lon = _convert_gps(gps_ifd.get(piexif.GPSIFD.GPSLongitude),
                               gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef, b'E'))
            result["gps_lat"] = lat
            result["gps_lon"] = lon
    except Exception:
        pass
    return result


def _convert_gps(coord, ref) -> float:
    if not coord:
        return None
    try:
        degrees = coord[0][0] / coord[0][1]
        minutes = coord[1][0] / coord[1][1] / 60
        seconds = coord[2][0] / coord[2][1] / 3600
        decimal = degrees + minutes + seconds
        ref_str = ref.decode() if isinstance(ref, bytes) else str(ref)
        if ref_str in ['S', 'W']:
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def _analyze_timestamp(exif_data: dict, claim_date: str = None) -> dict:
    if not exif_data["has_exif"]:
        return {
            "fraud_score": 0.65,
            "flag": "No EXIF data — metadata may have been stripped",
            "datetime_original": None,
            "interpretation": "Absence of EXIF suggests possible metadata scrubbing"
        }
    if not exif_data["datetime_original"]:
        return {
            "fraud_score": 0.5,
            "flag": "DateTimeOriginal missing from EXIF",
            "datetime_original": None,
            "interpretation": "Photo capture timestamp is unavailable"
        }
    dt_str = exif_data["datetime_original"]
    fraud_score = 0.0
    flag = None
    interpretation = f"Photo taken: {dt_str}"
    try:
        photo_dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        if claim_date:
            claim_dt = datetime.strptime(claim_date, "%Y-%m-%d")
            days_diff = (claim_dt - photo_dt).days
            if days_diff < 0:
                fraud_score = 0.8
                flag = f"Photo timestamp is {abs(days_diff)} days AFTER claim date"
                interpretation = "Image appears to postdate the reported incident"
            elif days_diff > 30:
                fraud_score = 0.75
                flag = f"Photo taken {days_diff} days before claimed incident — possible pre-existing damage"
                interpretation = "This photo may show pre-existing damage"
            elif days_diff > 7:
                fraud_score = 0.35
                flag = f"Photo taken {days_diff} days before claim submission"
                interpretation = "Minor temporal discrepancy"
        else:
            now = datetime.now()
            age_days = (now - photo_dt).days
            if age_days > 365:
                fraud_score = 0.4
                flag = f"Photo is {age_days} days old — possibly recycled"
    except ValueError:
        fraud_score = 0.3
        interpretation = "Could not parse timestamp format"
    return {
        "fraud_score": round(fraud_score, 3),
        "flag": flag,
        "datetime_original": dt_str,
        "interpretation": interpretation
    }


def _analyze_gps(exif_data: dict, claim_location: str = None) -> dict:
    if not exif_data["has_gps"]:
        return {
            "fraud_score": 0.3,
            "flag": "No GPS data in image",
            "coordinates": None,
            "interpretation": "Cannot verify incident location"
        }
    lat = exif_data["gps_lat"]
    lon = exif_data["gps_lon"]
    if lat is None or lon is None:
        return {
            "fraud_score": 0.3,
            "flag": "GPS data present but coordinates invalid",
            "coordinates": None,
            "interpretation": "GPS tags found but unreadable"
        }
    coords_str = f"{lat:.4f}, {lon:.4f}"
    fraud_score = 0.0
    flag = None
    interpretation = f"Image captured at: {coords_str}"
    if abs(lat) < 0.01 and abs(lon) < 0.01:
        fraud_score = 0.8
        flag = "GPS coordinates are 0,0 — likely spoofed"
        interpretation = "Null Island coordinates detected"
    return {
        "fraud_score": round(fraud_score, 3),
        "flag": flag,
        "coordinates": {"lat": lat, "lon": lon},
        "coordinates_str": coords_str,
        "interpretation": interpretation
    }


def _analyze_metadata_integrity(exif_data: dict, image: Image.Image) -> dict:
    score = 0.0
    flags = []
    if not exif_data["has_exif"]:
        score += 0.5
        flags.append("No EXIF data detected")
    suspicious_software = ["photoshop", "gimp", "lightroom", "midjourney",
                           "stable diffusion", "dall-e", "adobe", "canva"]
    sw = (exif_data.get("software") or "").lower()
    for s in suspicious_software:
        if s in sw:
            score += 0.6
            flags.append(f"Editing software detected: {exif_data['software']}")
            break
    if exif_data["has_exif"] and not exif_data["make"]:
        score += 0.25
        flags.append("Camera make/model missing")
    return {
        "fraud_score": round(min(score, 1.0), 3),
        "flag": "; ".join(flags) if flags else None,
        "has_exif": exif_data["has_exif"],
        "camera": f"{exif_data.get('make', '')} {exif_data.get('model', '')}".strip() or None,
        "software": exif_data.get("software"),
        "interpretation": "Metadata intact" if score < 0.2 else "; ".join(flags)
    }


def _summarize_exif(exif_data: dict) -> dict:
    return {
        "has_exif": exif_data["has_exif"],
        "has_gps": exif_data["has_gps"],
        "capture_time": exif_data.get("datetime_original"),
        "camera": f"{exif_data.get('make') or ''} {exif_data.get('model') or ''}".strip() or "Unknown",
        "software": exif_data.get("software", "None")
    }


def _score_label(score: float) -> str:
    if score >= 0.75:
        return "HIGH_RISK"
    elif score >= 0.45:
        return "MEDIUM_RISK"
    elif score >= 0.2:
        return "LOW_RISK"
    else:
        return "CLEAN"
