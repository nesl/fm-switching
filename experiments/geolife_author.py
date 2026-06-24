"""
GeoLife question authoring — mechanical template-based approach.
For each weekly timeline, generates non-salient far-distance recall questions.

Templates:
  T1: "What stop came immediately before [place] on [day]?" — answer = preceding stop label
  T2: "What was the first named stop on [day], not counting home or work?" — answer = first non-HW stop that day
  T3: "What stop immediately followed [place] on [day]?" — answer = next stop label
  T4: "What transport mode was used to get to [place] on [day]?" — answer = mode string (labeled users only)
  T5: "Which stop was visited on [day1] but not on [day2]?" — answer = singleton-day stop

Non-salient enforcement:
  - Answer must NOT be the user's home label(s) or work label(s)
  - Both anchor and answer must be "specific" type (named venue) or "road" type with a named road
  - Exclude "Unknown area" and failed geocodes

Far-distance enforcement:
  - Queried event must be in Mon, Tue, or Wed of the week (not last 2 days)
  - For window-5 condition: last 5 stops rarely include Mon-Wed events in a 40-stop week

Output: JSON list of question records, each with:
  - q_uid, user_id, week_key, template, question, gold, evidence_stop_idx,
    evidence_distance_from_end, full_context (timeline_text)
"""
import json
from pathlib import Path
from datetime import datetime

TIMELINES_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife_weekly_timelines.json"
OUT_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife_questions.json"

# Home/work label fragments to exclude from answers (substring match, case-insensitive)
HOME_WORK_FRAGMENTS = {
    "000": ["shuangqing road", "zijing road, qinghuayuan"],
    "020": ["zhongguancun", "中关村地下环廊", "中关村南四街", "danling", "cnic"],
    "052": ["datun road", "chaoyangmen inner street", "麦叔的铺子"],
}

GENERIC_FRAGMENTS = ["unknown area", "timeout", "not_found", "failed"]

def is_salient_or_generic(label, user_id):
    label_l = label.lower()
    for frag in GENERIC_FRAGMENTS:
        if frag in label_l:
            return True
    hw = HOME_WORK_FRAGMENTS.get(user_id, [])
    for frag in hw:
        if frag.lower() in label_l:
            return True
    return False

def is_usable_label(label, user_id):
    """True if label is specific enough to be a question anchor or answer."""
    if not label or len(label) < 3:
        return False
    return not is_salient_or_generic(label, user_id)

def day_name(iso_str):
    return datetime.fromisoformat(iso_str).strftime("%A")

def format_time(iso_str):
    return datetime.fromisoformat(iso_str).strftime("%H:%M")

def generate_questions(week, max_q=10):
    uid = week["user_id"]
    wk = week["week_key"]
    stops = week["stops"]
    n = len(stops)
    full_ctx = week["timeline_text"]
    questions = []

    # ── T1: "What stop came immediately BEFORE [place]?" ────────────────────
    for i in range(1, n):
        s = stops[i]
        prev = stops[i-1]
        anchor_day = day_name(s["arrival"])
        # Only Mon, Tue, Wed (far from end)
        if anchor_day not in ("Monday", "Tuesday", "Wednesday"):
            continue
        if not is_usable_label(s["place_label"], uid):
            continue
        if not is_usable_label(prev["place_label"], uid):
            continue
        # evidence_distance: how many stops from the end
        dist_from_end = n - i
        q_text = (f"In the weekly timeline below, what named stop came immediately before "
                  f"'{s['place_label']}' on {anchor_day}?")
        questions.append({
            "q_uid": f"{uid}_{wk}_T1_{i}",
            "user_id": uid, "week_key": wk,
            "template": "T1_before",
            "question": q_text,
            "gold": prev["place_label"],
            "anchor": s["place_label"],
            "anchor_stop_idx": i,
            "evidence_stop_idx": i - 1,
            "evidence_distance_from_end": dist_from_end,
            "full_context": full_ctx,
            "n_stops_in_week": n,
        })

    # ── T3: "What stop came immediately AFTER [place]?" ─────────────────────
    for i in range(0, n - 1):
        s = stops[i]
        nxt = stops[i+1]
        anchor_day = day_name(s["arrival"])
        if anchor_day not in ("Monday", "Tuesday", "Wednesday"):
            continue
        if not is_usable_label(s["place_label"], uid):
            continue
        if not is_usable_label(nxt["place_label"], uid):
            continue
        dist_from_end = n - i - 1
        q_text = (f"In the weekly timeline below, what named stop came immediately after "
                  f"'{s['place_label']}' on {anchor_day}?")
        questions.append({
            "q_uid": f"{uid}_{wk}_T3_{i}",
            "user_id": uid, "week_key": wk,
            "template": "T3_after",
            "question": q_text,
            "gold": nxt["place_label"],
            "anchor": s["place_label"],
            "anchor_stop_idx": i,
            "evidence_stop_idx": i + 1,
            "evidence_distance_from_end": n - i - 1,
            "full_context": full_ctx,
            "n_stops_in_week": n,
        })

    # ── T4: "What transport mode was used to GET to [place] on [day]?" ───────
    for i in range(1, n):
        s = stops[i]
        if s.get("mode") is None:
            continue
        anchor_day = day_name(s["arrival"])
        if anchor_day not in ("Monday", "Tuesday", "Wednesday"):
            continue
        if not is_usable_label(s["place_label"], uid):
            continue
        dist_from_end = n - i
        q_text = (f"In the weekly timeline below, what transport mode was used to travel to "
                  f"'{s['place_label']}' on {anchor_day}?")
        questions.append({
            "q_uid": f"{uid}_{wk}_T4_{i}",
            "user_id": uid, "week_key": wk,
            "template": "T4_mode",
            "question": q_text,
            "gold": s["mode"],
            "anchor": s["place_label"],
            "anchor_stop_idx": i,
            "evidence_stop_idx": i,
            "evidence_distance_from_end": dist_from_end,
            "full_context": full_ctx,
            "n_stops_in_week": n,
        })

    # Deduplicate: keep at most 2 questions per anchor place to avoid repetition
    seen_anchors = {}
    deduped = []
    for q in questions:
        anchor = q["anchor"]
        count = seen_anchors.get(anchor, 0)
        if count < 2:
            seen_anchors[anchor] = count + 1
            deduped.append(q)

    # Sort by evidence_distance (farthest first), take top max_q
    deduped.sort(key=lambda q: q["evidence_distance_from_end"], reverse=True)
    return deduped[:max_q]

def main():
    with open(TIMELINES_FILE) as f:
        weeks = json.load(f)

    # Focus on richer weeks (≥15 total stops, ≥300 tokens)
    rich_weeks = [w for w in weeks if w["n_stops"] >= 15 and w["token_count_approx"] >= 200]
    print(f"Total weeks: {len(weeks)}, rich weeks (≥15 stops, ≥200 tokens): {len(rich_weeks)}")

    all_questions = []
    for w in rich_weeks:
        qs = generate_questions(w, max_q=10)
        all_questions.extend(qs)
        print(f"  User {w['user_id']} | {w['week_key']} | {w['n_stops']} stops | {w['token_count_approx']} tok | {len(qs)} questions authored")

    # Assign sequential UIDs
    for i, q in enumerate(all_questions):
        q["q_uid"] = f"geo_{i:04d}"

    print(f"\nTotal questions authored: {len(all_questions)}")
    # Template distribution
    from collections import Counter
    tmpl_counts = Counter(q["template"] for q in all_questions)
    for t, c in tmpl_counts.most_common():
        print(f"  {t}: {c}")

    # Distance distribution
    dists = [q["evidence_distance_from_end"] for q in all_questions]
    dists_sorted = sorted(dists, reverse=True)
    print(f"\nEvidence distance from end (in stops):")
    print(f"  Max: {max(dists)}, Median: {dists_sorted[len(dists)//2]}, Min: {min(dists)}")

    with open(OUT_FILE, "w") as f:
        json.dump(all_questions, f, indent=2)
    print(f"\nSaved {len(all_questions)} questions to {OUT_FILE}")

    # Show 5 sample questions
    print("\n=== Sample Questions ===")
    for q in all_questions[:5]:
        print(f"  Q: {q['question']}")
        print(f"  A: {q['gold']}")
        print(f"  Week: {q['week_key']}, dist_from_end: {q['evidence_distance_from_end']} stops")
        print()

if __name__ == "__main__":
    main()
