"""
GeoLife weekly timeline renderer.
Users: 000, 020, 052 (confirmed urban Beijing).
Output: JSON list of weekly timeline records, each with:
  - user_id, week_start, week_end
  - stops: list of {lat, lon, arrival, departure, duration_min, place_label, place_type, mode}
  - timeline_text: serialized event sequence LLM reads as context
  - token_count_approx
"""
import os, math, time, json, datetime, re
from pathlib import Path
from collections import defaultdict

BASE = Path("/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife/Geolife Trajectories 1.3/Data")
CACHE_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geocode_cache.json"
OUT_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife_weekly_timelines.json"

USERS = ["000", "020", "052"]
BEIJING_BBOX = (39.5, 40.5, 115.5, 117.0)

# ── geometry ──────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2*R*math.asin(math.sqrt(a))

def cache_key(lat, lon):
    # 3 decimal places ≈ 100m precision — coarser than 200m radius is fine
    return f"{round(lat,3)},{round(lon,3)}"

# ── PLT loader ────────────────────────────────────────────────────────────────

def load_plt(path):
    pts = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i < 6: continue
            parts = line.strip().split(',')
            if len(parts) < 7: continue
            try:
                lat, lon = float(parts[0]), float(parts[1])
                dt = datetime.datetime.strptime(f"{parts[5]} {parts[6]}", "%Y-%m-%d %H:%M:%S")
                pts.append((lat, lon, dt))
            except:
                pass
    return pts

def load_user_pts(uid):
    traj_dir = BASE / uid / "Trajectory"
    all_pts = []
    for plt_file in sorted(traj_dir.glob("*.plt")):
        pts = load_plt(plt_file)
        # Filter to Beijing bbox only
        pts = [p for p in pts if BEIJING_BBOX[0]<=p[0]<=BEIJING_BBOX[1] and BEIJING_BBOX[2]<=p[1]<=BEIJING_BBOX[3]]
        all_pts.extend(pts)
    all_pts.sort(key=lambda p: p[2])
    return all_pts

# ── stay-point detection (Li et al. 2008) ────────────────────────────────────

def detect_stay_points(pts, radius_m=200, min_time_min=20):
    stays = []
    i, n = 0, len(pts)
    while i < n - 1:
        j = i + 1
        while j < n:
            if haversine_m(pts[i][0], pts[i][1], pts[j][0], pts[j][1]) > radius_m:
                break
            j += 1
        duration_min = (pts[j-1][2] - pts[i][2]).total_seconds() / 60.0
        if duration_min >= min_time_min:
            lat_c = sum(p[0] for p in pts[i:j]) / (j-i)
            lon_c = sum(p[1] for p in pts[i:j]) / (j-i)
            stays.append({
                "lat": lat_c, "lon": lon_c,
                "arrival": pts[i][2],
                "departure": pts[j-1][2],
                "duration_min": round(duration_min, 1)
            })
            i = j
        else:
            i += 1
    return stays

# ── transport mode from labels.txt ───────────────────────────────────────────

def load_labels(uid):
    """Returns list of (start_dt, end_dt, mode)."""
    labels_file = BASE / uid / "labels.txt"
    if not labels_file.exists():
        return []
    labels = []
    with open(labels_file) as f:
        for i, line in enumerate(f):
            if i == 0: continue
            parts = line.strip().split('\t')
            if len(parts) < 3: continue
            try:
                start = datetime.datetime.strptime(parts[0], "%Y/%m/%d %H:%M:%S")
                end = datetime.datetime.strptime(parts[1], "%Y/%m/%d %H:%M:%S")
                mode = parts[2].strip()
                labels.append((start, end, mode))
            except:
                pass
    return labels

def get_mode_for_travel(labels, travel_start, travel_end):
    """Return the dominant transport mode for a travel segment."""
    if not labels:
        return None
    overlaps = []
    for (ls, le, mode) in labels:
        overlap_start = max(ls, travel_start)
        overlap_end = min(le, travel_end)
        if overlap_end > overlap_start:
            dur = (overlap_end - overlap_start).total_seconds()
            overlaps.append((dur, mode))
    if not overlaps:
        return None
    return max(overlaps, key=lambda x: x[0])[1]

# ── geocoding ─────────────────────────────────────────────────────────────────

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut
    _geocoder = Nominatim(user_agent="fm-switching-geolife-microgate", timeout=10)
    HAVE_GEOPY = True
except ImportError:
    HAVE_GEOPY = False

_cache = {}

def load_cache():
    global _cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            _cache = json.load(f)
    print(f"  Geocache loaded: {len(_cache)} entries")

def save_cache():
    with open(CACHE_FILE, 'w') as f:
        json.dump(_cache, f, indent=2)

def reverse_geocode(lat, lon):
    key = cache_key(lat, lon)
    if key in _cache:
        return _cache[key]
    if not HAVE_GEOPY:
        _cache[key] = {"label": "UNKNOWN", "type": "failed"}
        return _cache[key]
    for attempt in range(3):
        try:
            loc = _geocoder.reverse(f"{lat}, {lon}", language="en", zoom=18)
            time.sleep(1.1)
            result = _parse_geocode(loc)
            _cache[key] = result
            save_cache()
            return result
        except (GeocoderTimedOut, Exception) as e:
            if attempt < 2:
                time.sleep(2)
            else:
                result = {"label": "TIMEOUT", "type": "failed"}
                _cache[key] = result
                return result

def _parse_geocode(loc):
    if loc is None:
        return {"label": "NOT_FOUND", "type": "failed"}
    addr = loc.raw.get("address", {})
    osm_class = loc.raw.get("class", "")

    venue = (addr.get("amenity") or addr.get("tourism") or addr.get("shop") or
             addr.get("railway") or addr.get("leisure") or addr.get("building") or
             addr.get("office") or addr.get("university") or addr.get("college") or
             addr.get("subway_entrance"))

    if venue and len(venue.strip()) > 1:
        cat = osm_class or "venue"
        return {"label": venue.strip(), "type": "specific", "category": cat}

    road = addr.get("road") or addr.get("pedestrian") or addr.get("cycleway")
    suburb = addr.get("suburb") or addr.get("neighbourhood") or ""
    if road:
        label = road + (f", {suburb}" if suburb else "")
        return {"label": label, "type": "road", "category": "road"}

    district = (addr.get("city_district") or addr.get("county") or
                addr.get("suburb") or addr.get("district") or "")
    return {"label": district or "Unknown area", "type": "district", "category": "district"}

# ── group by ISO week ─────────────────────────────────────────────────────────

def group_by_week(stays):
    """Returns dict of iso_week_str -> list of stays."""
    by_week = defaultdict(list)
    for s in stays:
        iso = s["arrival"].isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        by_week[week_key].append(s)
    return dict(by_week)

# ── text serializer ───────────────────────────────────────────────────────────

def serialize_timeline(stops_with_meta):
    """
    stops_with_meta: list of stops sorted by arrival, each with:
      arrival, departure, duration_min, place_label, place_type, mode (travel to this stop)
    Returns: (timeline_text, token_count_approx)
    """
    lines = []
    for i, s in enumerate(stops_with_meta):
        arr = s["arrival"].strftime("%a %Y-%m-%d %H:%M")
        dep = s["departure"].strftime("%H:%M")
        dur = int(s["duration_min"])
        place = s["place_label"]
        mode = s.get("mode")

        if i == 0:
            travel_str = ""
        elif mode:
            travel_str = f" [via {mode}]"
        else:
            travel_str = ""

        lines.append(f"{arr} – {dep}{travel_str}: {place} ({dur} min)")

    text = "\n".join(lines)
    # Approximate token count: ~4 chars/token for mixed content
    token_count = len(text) // 4
    return text, token_count

# ── identify home / work heuristic ───────────────────────────────────────────

def identify_home_work(stops_all):
    """
    Heuristic: home = location with most night-time dwell (00:00-06:00),
               work = highest daytime dwell (09:00-18:00), excluding home.
    Returns (home_key, work_key) as cache_key strings.
    """
    night_dwell = defaultdict(float)
    day_dwell = defaultdict(float)

    for s in stops_all:
        key = cache_key(s["lat"], s["lon"])
        arr, dep = s["arrival"], s["departure"]
        dur = s["duration_min"]

        arr_h = arr.hour + arr.minute/60
        dep_h = dep.hour + dep.minute/60

        # Rough night/day overlap (simplified: use midpoint)
        mid_h = (arr_h + dep_h) / 2
        if mid_h < 6 or mid_h > 22:
            night_dwell[key] += dur
        elif 9 <= mid_h <= 18:
            day_dwell[key] += dur

    home_key = max(night_dwell, key=night_dwell.get) if night_dwell else None

    # Work = top daytime dwell excluding home
    day_dwell_nohome = {k: v for k, v in day_dwell.items() if k != home_key}
    work_key = max(day_dwell_nohome, key=day_dwell_nohome.get) if day_dwell_nohome else None

    return home_key, work_key

# ── main ──────────────────────────────────────────────────────────────────────

def render_user(uid):
    print(f"\n=== Rendering User {uid} ===")
    pts = load_user_pts(uid)
    labels = load_labels(uid)
    print(f"  Loaded {len(pts)} GPS points, {len(labels)} mode labels")

    # Detect all stay-points
    stays_raw = detect_stay_points(pts, radius_m=200, min_time_min=20)
    print(f"  Stay-points detected: {len(stays_raw)}")

    # Geocode all unique locations (cached)
    unique_locs = set(cache_key(s["lat"], s["lon"]) for s in stays_raw)
    new_geocodes = [k for k in unique_locs if k not in _cache]
    print(f"  Unique locations: {len(unique_locs)}, need to geocode: {len(new_geocodes)}")

    for i, s in enumerate(stays_raw):
        key = cache_key(s["lat"], s["lon"])
        if key not in _cache:
            result = reverse_geocode(s["lat"], s["lon"])
            if i % 5 == 0:
                print(f"  Geocoded {i+1}/{len(stays_raw)}: {result['label']}")
        geo = _cache.get(cache_key(s["lat"], s["lon"]), {"label": "Unknown", "type": "failed"})
        s["place_label"] = geo["label"]
        s["place_type"] = geo["type"]

    # Identify home/work for non-salient filtering
    home_key, work_key = identify_home_work(stays_raw)
    home_label = _cache.get(home_key, {}).get("label", "Home") if home_key else "Home"
    work_label = _cache.get(work_key, {}).get("label", "Work") if work_key else "Work"
    print(f"  Heuristic home: {home_label}")
    print(f"  Heuristic work: {work_label}")

    # Add transport mode for each stop (mode of travel TO this stop)
    for i, s in enumerate(stays_raw):
        if i == 0:
            s["mode"] = None
            continue
        travel_start = stays_raw[i-1]["departure"]
        travel_end = s["arrival"]
        s["mode"] = get_mode_for_travel(labels, travel_start, travel_end)

    # Group by week
    by_week = group_by_week(stays_raw)
    print(f"  Weeks with data: {len(by_week)}")

    weekly_records = []
    for week_key in sorted(by_week.keys()):
        week_stays = sorted(by_week[week_key], key=lambda s: s["arrival"])

        # Count non-home-work stops
        non_hw_stops = [s for s in week_stays
                        if cache_key(s["lat"], s["lon"]) not in (home_key, work_key)]

        # Skip weeks with < 3 stops (insufficient for questions)
        if len(week_stays) < 3:
            continue

        # Serialize timeline
        timeline_text, tok_count = serialize_timeline(week_stays)

        # Convert datetimes for JSON
        stops_json = []
        for s in week_stays:
            stops_json.append({
                "lat": round(s["lat"], 5),
                "lon": round(s["lon"], 5),
                "arrival": s["arrival"].isoformat(),
                "departure": s["departure"].isoformat(),
                "duration_min": s["duration_min"],
                "place_label": s["place_label"],
                "place_type": s["place_type"],
                "mode": s.get("mode"),
                "is_home": cache_key(s["lat"], s["lon"]) == home_key,
                "is_work": cache_key(s["lat"], s["lon"]) == work_key,
            })

        # Week start/end from data
        week_start = week_stays[0]["arrival"].date().isoformat()
        week_end = week_stays[-1]["departure"].date().isoformat()

        weekly_records.append({
            "user_id": uid,
            "week_key": week_key,
            "week_start": week_start,
            "week_end": week_end,
            "n_stops": len(week_stays),
            "n_non_hw_stops": len(non_hw_stops),
            "home_label": home_label,
            "work_label": work_label,
            "stops": stops_json,
            "timeline_text": timeline_text,
            "token_count_approx": tok_count,
        })

    return weekly_records

def main():
    load_cache()
    all_weeks = []
    for uid in USERS:
        try:
            recs = render_user(uid)
            all_weeks.extend(recs)
            print(f"  → {len(recs)} weekly records for User {uid}")
        except Exception as e:
            print(f"  ERROR rendering User {uid}: {e}")

    # Token length distribution
    toks = [r["token_count_approx"] for r in all_weeks]
    if toks:
        toks_sorted = sorted(toks)
        print(f"\n=== Token length distribution ({len(toks)} weeks) ===")
        print(f"  Min: {min(toks)}")
        print(f"  P10: {toks_sorted[len(toks_sorted)//10]}")
        print(f"  Median: {toks_sorted[len(toks_sorted)//2]}")
        print(f"  P75: {toks_sorted[3*len(toks_sorted)//4]}")
        print(f"  P90: {toks_sorted[9*len(toks_sorted)//10]}")
        print(f"  Max: {max(toks)}")

    # Stops per week distribution
    stops = [r["n_stops"] for r in all_weeks]
    nhw = [r["n_non_hw_stops"] for r in all_weeks]
    print(f"\n=== Stop counts per week ===")
    print(f"  Mean total stops/week: {sum(stops)/len(stops):.1f}")
    print(f"  Mean non-HW stops/week: {sum(nhw)/len(nhw):.1f}")
    print(f"  Median non-HW: {sorted(nhw)[len(nhw)//2]}")
    print(f"  Weeks with >=5 non-HW stops: {sum(1 for n in nhw if n>=5)}/{len(nhw)}")

    with open(OUT_FILE, 'w') as f:
        json.dump(all_weeks, f, indent=2)
    print(f"\nSaved {len(all_weeks)} weekly timeline records to {OUT_FILE}")

    # Show 3 sample timelines
    print("\n=== Sample timeline (User 000, first rich week) ===")
    sample = next((r for r in all_weeks if r["user_id"]=="000" and r["n_non_hw_stops"]>=4), None)
    if sample:
        print(f"  Week: {sample['week_key']} ({sample['n_stops']} stops, {sample['n_non_hw_stops']} non-HW, ~{sample['token_count_approx']} tokens)")
        print(sample["timeline_text"])

if __name__ == "__main__":
    main()
