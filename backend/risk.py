"""Transparent risk score 0-100 = severity + rain + slope + exposure."""


def score(severity: int, rain_72h: float | None, slope_deg: float | None, exposure: dict | None) -> dict:
    sev_pts = max(0, min(5, int(severity or 0))) * 8  # max 40

    r = rain_72h or 0
    rain_pts = 25 if r > 50 else 15 if r >= 20 else 5  # max 25

    s = slope_deg if slope_deg is not None else 0
    slope_pts = 20 if s > 35 else 12 if s >= 25 else 6 if s >= 15 else 2  # max 20

    c = (exposure or {}).get("counts", {})
    exp_pts = min(15, 3 * (c.get("schools", 0) + c.get("health", 0)) + c.get("bridges", 0))  # max 15

    total = sev_pts + rain_pts + slope_pts + exp_pts
    level = "high" if total >= 70 else "medium" if total >= 40 else "low"
    return {"score": total, "level": level,
            "breakdown": {"severity": sev_pts, "rain": rain_pts, "slope": slope_pts, "exposure": exp_pts}}
