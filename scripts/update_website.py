"""
Update website data — run from YOUR LOCAL MACHINE (residential IP required).

Usage:
    python scripts/update_website.py           # real scraping
    python scripts/update_website.py --demo    # demo data (no network needed)

What it does:
  1. Runs scrapers (or loads demo data)
  2. Adds lat/lng coordinates per complex
  3. Saves data.json
  4. Copies data.json to the gh-pages worktree
  5. Commits and pushes to gh-pages → site updates at https://ko8a.github.io/Kobylandy/
"""

import sys, os, json, subprocess, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_OUT = os.path.join(REPO_ROOT, "data", "processed", "apartments_web.json")
GHPAGES_DIR = os.path.join(REPO_ROOT, ".ghpages_worktree")

# Approximate Astana lat/lng per district keyword → complex name → coords
COMPLEX_COORDS = {
    "bi plaza":           (51.1641, 71.4681),
    "bi city":            (51.1288, 71.4317),
    "bi residence":       (51.1649, 71.4712),
    "bi sky":             (51.1681, 71.4496),
    "alatau city":        (51.1574, 71.4819),
    "triumph":            (51.1490, 71.3872),
    "birlik":             (51.1500, 71.3897),
    "astra":              (51.1349, 71.4415),
    "nova":               (51.1100, 71.4539),
    "sensata":            (51.1711, 71.4283),
    "rams city":          (51.1511, 71.3950),
    "rams expo":          (51.1699, 71.4169),
    "rams smart":         (51.1436, 71.3894),
    "gbg park":           (51.1623, 71.4579),
    "gbg tower":          (51.1678, 71.4454),
    "gbg smart":          (51.1323, 71.4456),
    "свой дом плюс":      (51.1191, 71.4172),
    "expo residence":     (51.1692, 71.4160),
    "экспо резиденс":     (51.1692, 71.4160),
    "green quarter":      (51.1215, 71.4136),
    "sat nova":           (51.1543, 71.3816),
    "sat premium":        (51.1632, 71.4362),
    "sat comfort":        (51.1279, 71.4379),
    "elita residence":    (51.1601, 71.4595),
    "elita gardens":      (51.1689, 71.4159),
    "capital park":       (51.1652, 71.4729),
    "park view":          (51.1631, 71.4689),
    "bazis standard":     (51.1236, 71.4471),
    "bazis city":         (51.1256, 71.4434),
    "eurasia sky":        (51.1618, 71.4648),
    "miras park":         (51.1089, 71.4629),
    "nur city":           (51.1105, 71.4646),
    "tamos comfort":      (51.1305, 71.4543),
    "tamos premium":      (51.1659, 71.4743),
    "asyl park":          (51.1463, 71.3747),
    "askar residence":    (51.1433, 71.3766),
    "grand expo":         (51.1714, 71.4199),
    "caspian towers":     (51.1591, 71.4615),
    "altai city":         (51.1151, 71.4229),
    "orda residence":     (51.1645, 71.4386),
    "saryarka park":      (51.1509, 71.3878),
    "prime residence":    (51.1629, 71.4500),
    "alma residence":     (51.1327, 71.4385),
    "nurly tobe":         (51.1083, 71.4499),
    "komfort plus":       (51.1299, 71.4500),
}

DISTRICT_FALLBACK = {
    "есиль":       (51.1650, 71.4450),
    "алматинский": (51.1280, 71.4400),
    "байконур":    (51.1490, 71.3880),
    "нура":        (51.1095, 71.4560),
}


def get_coords(apt: dict, idx: int) -> tuple:
    name = (apt.get("название_жк") or "").lower()
    district = (apt.get("район_адрес") or "").lower()

    for key, coords in COMPLEX_COORDS.items():
        if key in name:
            offset = (idx % 11 - 5) * 0.00015
            return (coords[0] + offset, coords[1] + offset * 0.7)

    for key, coords in DISTRICT_FALLBACK.items():
        if key in district:
            offset = (idx % 17 - 8) * 0.0008
            return (coords[0] + offset, coords[1] + offset)

    return (51.1801 + (idx % 7 - 3) * 0.005, 71.4460 + (idx % 5 - 2) * 0.005)


def run_scrapers_demo():
    from scrapers.demo_data import get_demo_apartments
    return get_demo_apartments()


def run_scrapers_real():
    from main import run_scrapers
    return run_scrapers()


def setup_ghpages_worktree():
    if os.path.exists(GHPAGES_DIR):
        return
    subprocess.run(
        ["git", "worktree", "add", GHPAGES_DIR, "gh-pages"],
        cwd=REPO_ROOT, check=True
    )


def update_ghpages(data_path: str):
    setup_ghpages_worktree()
    dest = os.path.join(GHPAGES_DIR, "data.json")
    shutil.copy2(data_path, dest)
    subprocess.run(["git", "add", "data.json"], cwd=GHPAGES_DIR, check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=GHPAGES_DIR
    )
    if result.returncode == 0:
        print("No changes to data.json — skipping commit.")
        return False
    from datetime import datetime
    msg = f"Update apartment data — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", msg],
        cwd=GHPAGES_DIR, check=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "gh-pages"],
        cwd=GHPAGES_DIR, check=True
    )
    return True


def main():
    demo = "--demo" in sys.argv

    print("=" * 60)
    print("Kobylandy — website data update")
    print("=" * 60)

    if demo:
        print("Mode: DEMO (no scraping)")
        apartments = run_scrapers_demo()
    else:
        print("Mode: LIVE (scraping all sites — residential IP required)")
        print("Sites blocked from cloud/datacenter IPs. Run from home network.")
        apartments = run_scrapers_real()

    # Flatten if scrapers returned list-of-lists
    flat = []
    for item in apartments:
        if isinstance(item, dict):
            flat.append(item)
        elif isinstance(item, list):
            flat.extend(x for x in item if isinstance(x, dict))
    apartments = flat

    if not apartments:
        print("ERROR: no apartments returned. Use --demo or check network.")
        sys.exit(1)

    print(f"Fetched: {len(apartments)} apartments")

    # Add lat/lng
    for i, apt in enumerate(apartments):
        lat, lng = get_coords(apt, i)
        apt["lat"] = round(lat, 6)
        apt["lng"] = round(lng, 6)
        apt["id"] = i

    os.makedirs(os.path.dirname(DATA_OUT), exist_ok=True)
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(apartments, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved: {DATA_OUT} ({os.path.getsize(DATA_OUT) // 1024} KB)")

    print("Updating gh-pages branch...")
    pushed = update_ghpages(DATA_OUT)
    if pushed:
        print("\nDone! Site will update in ~30 seconds:")
        print("  https://ko8a.github.io/Kobylandy/")
    else:
        print("Done (no new data).")


if __name__ == "__main__":
    main()
