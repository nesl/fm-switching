# Orin notes (analysis host)

## 2026-11-27: d190_d192_poll.sh stopped by user ruling

- The scratchpad loop `d190_d192_poll.sh` (PID 1445420, started about 2.9 days earlier, 30 min interval) was stopped on 2026-11-27 by user ruling. It was killed by PID only; its child `sleep 1800` (PID 1744532) was also stopped. Neither is to be restarted.
- Reason: its figdata regeneration dropped 21 rows from `reports/figdata/F1.csv` (rung 3, eco-llm, kvflow, device-only) and left the tracked file dirty, so every rebase failed ("cannot rebase: You have unstaged changes").
- Its log is archived unchanged at `scratchpad/d190_d192_poll.log.2026-11-27.bak` (the live log is kept beside it).
- The modified file is preserved, untracked, at `reports/figdata/F1.csv.uncommitted-2026-11-27`. The tracked file was restored with `git checkout --` to HEAD. Nothing was deleted.
