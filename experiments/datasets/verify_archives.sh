#!/usr/bin/env bash
# Verify pulled split-tar archives without extracting: sha256 of every part vs the HF LFS sha256 recorded in flash's
# preflight.json (pinned commit), then stream the concatenated parts through `tar -t` (no files written) and count
# members (flash's archives.json reports the member count). Single process, nice 19 / idle IO class.
# Usage: verify_archives.sh <dataset> <hf repo id> <part glob relative to dataset dir>
# Example: verify_archives.sh ovo_bench JoeLeelyf/OVO-Bench 'hf/src_videos.tar.part*'
set -u
ds=$1; repo=$2; glob=$3
cd /home/pragya/data/datasets/$ds
OUT=/home/pragya/Desktop/fm-switching/results/datasets/archives_check_h100_$ds.json
PRE=/home/pragya/data/flash/meta/preflight.json
tmp=$(mktemp)
for p in $([ "${SKIP_SHA:-0}" = "1" ] || echo $glob); do
  h=$(nice -n 19 ionice -c3 sha256sum "$p" | cut -d' ' -f1)
  exp=$(python3 -c "import json,sys; f={x['path']:x for x in json.load(open('$PRE'))['$repo']['files']}; print(f.get('${p#hf/}',{}).get('lfs_sha256'))")
  size=$(stat -c %s "$p")
  echo "{\"part\": \"$p\", \"size\": $size, \"sha256\": \"$h\", \"hf_lfs_sha256\": \"$exp\", \"match\": $([ "$h" = "$exp" ] && echo true || echo false)}" >> $tmp
  echo "$p sha256 $([ "$h" = "$exp" ] && echo OK || echo MISMATCH)"
done
if [ "${SKIP_SHA:-0}" = "1" ] && [ -s "$OUT" ]; then python3 -c "import json; [print(json.dumps(p)) for p in json.load(open('$OUT'))['parts']]" > $tmp; fi
lst=$(mktemp)
cat $glob | nice -n 19 ionice -c3 tar -tv > $lst 2>/tmp/tar_err_$$; trc=${PIPESTATUS[1]}
members=$(wc -l < $lst); regular=$(grep -c '^-' $lst)
cp $lst /home/pragya/data/datasets/$ds/tar_listing_h100.txt; rm -f $lst
python3 - "$tmp" "$OUT" "$members" "$regular" "$trc" "/tmp/tar_err_$$" <<'EOF'
import json, sys
tmp, out, members, regular, trc, err = sys.argv[1:]
parts = [json.loads(l) for l in open(tmp)]
res = dict(parts=parts, all_parts_match=all(p["match"] for p in parts), tar_list_members=int(members),
           tar_list_regular_files=int(regular), tar_exit=int(trc), tar_stderr=open(err).read()[:500])
json.dump(res, open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "parts"}))
EOF
rm -f $tmp /tmp/tar_err_$$
