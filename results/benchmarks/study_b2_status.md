# StudyB2-h100 status

Updated: 2026-11-09 08:32 (written every 30 min by `experiments/benchmarks/b2_status.py`).

- **Stage:** Stage 4 HERBench: shard 0 queued (smoke, repeat control, Lite-v2 x6 arms, shard-0 full x6 arms); pulling parts 04-13.
- **Running step:** B2h0F_4BT (since 2026-11-09 03:30:11)
- **Next step:** B2h0F_8BT
- **Disk free (data disk):** 47.8 GiB (floor 20 GiB)
- **HALT:** none

## Coverage (error-free rows)

| dataset | arm | main | grey | coverage | files |
|---|---|---|---|---|---|
| ovo_rtv | 4BI | 15286 / 15286 | 200 / 200 | 100.0 % | 1 file(s), 26.3 MB |
| ovo_rtv | 8BI | 15286 / 15286 | 200 / 200 | 100.0 % | 1 file(s), 26.0 MB |
| ovo_rtv | 4BT | 15286 / 15286 | 200 / 200 | 100.0 % | 1 file(s), 33.2 MB |
| ovo_rtv | 8BT | 15286 / 15286 | 200 / 200 | 100.0 % | 1 file(s), 32.6 MB |
| streaming_bench | 4BI | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 11.7 MB |
| streaming_bench | 8BI | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 11.4 MB |
| streaming_bench | 32BI | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 11.7 MB |
| streaming_bench | 4BT | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 14.3 MB |
| streaming_bench | 8BT | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 14.3 MB |
| streaming_bench | 32BT | 6496 / 6500 | 200 / 200 | 99.9 % | 1 file(s), 13.5 MB |
| herbench | 4BI | 7325 / 28701 | 100 / 200 | 25.7 % | 1 file(s), 18.3 MB |
| herbench | 8BI | 7325 / 28701 | 100 / 200 | 25.7 % | 1 file(s), 18.1 MB |
| herbench | 32BI | 7325 / 28701 | 100 / 200 | 25.7 % | 1 file(s), 18.4 MB |
| herbench | 4BT | 6541 / 28701 | 100 / 200 | 23.0 % | 1 file(s), 28.3 MB |
| herbench | 8BT | 1971 / 28701 | 100 / 200 | 7.2 % | 1 file(s), 8.2 MB |
| herbench | 32BT | 1971 / 28701 | 100 / 200 | 7.2 % | 1 file(s), 7.5 MB |

## Queue

| step | state |
|---|---|
| B2o_smoke_4BI | 2026-11-06T19:30:54-08:00 |
| B2o_smoke_8BI | 2026-11-06T19:33:00-08:00 |
| B2o_smoke_4BT | 2026-11-06T19:35:22-08:00 |
| B2o_smoke_8BT | 2026-11-06T19:37:58-08:00 |
| B2o_4BI | 2026-11-06T21:01:14-08:00 |
| B2o_8BI | 2026-11-06T23:05:17-08:00 |
| B2o_4BT | 2026-11-07T03:09:04-08:00 |
| B2o_8BT | 2026-11-07T08:17:53-08:00 |
| B2o_latency | 2026-11-07T10:37:04-08:00 |
| B2s1_prep | 2026-11-07T11:07:41-08:00 |
| B2s1_smoke_4BI | 2026-11-07T11:08:39-08:00 |
| B2s1_smoke_8BI | 2026-11-07T11:09:41-08:00 |
| B2s1_smoke_32BI | 2026-11-07T11:11:29-08:00 |
| B2s1_smoke_4BT | 2026-11-07T11:12:49-08:00 |
| B2s1_smoke_8BT | 2026-11-07T11:14:27-08:00 |
| B2s1_smoke_32BT | 2026-11-07T11:17:14-08:00 |
| B2s1_mv_4BI | 2026-11-07T11:18:11-08:00 |
| B2s1_4BI | 2026-11-07T11:40:45-08:00 |
| B2s1_8BI | 2026-11-07T12:11:07-08:00 |
| B2s1_32BI | 2026-11-07T13:55:39-08:00 |
| B2s1_4BT | 2026-11-07T15:06:15-08:00 |
| B2s1_8BT | 2026-11-07T16:39:08-08:00 |
| B2s1_32BT | 2026-11-07T20:56:26-08:00 |
| B2s2_prep | 2026-11-07T21:23:36-08:00 |
| B2s2_4BI | 2026-11-07T22:03:56-08:00 |
| B2s2_8BI | 2026-11-07T22:16:44-08:00 |
| B2s2_32BI | 2026-11-07T23:00:48-08:00 |
| B2s2_4BT | 2026-11-07T23:16:45-08:00 |
| B2s2_8BT | 2026-11-07T23:41:20-08:00 |
| B2s2_32BT | 2026-11-08T00:45:24-08:00 |
| B2s3_prep | 2026-11-08T01:27:54-08:00 |
| B2s3_decode | 2026-11-08T01:31:37-08:00 |
| B2s3_4BI | 2026-11-08T02:16:20-08:00 |
| B2s3_8BI | 2026-11-08T02:29:12-08:00 |
| B2s3_32BI | 2026-11-08T03:12:43-08:00 |
| B2s3_4BT | 2026-11-08T03:28:55-08:00 |
| B2s3_8BT | 2026-11-08T03:51:08-08:00 |
| B2s3_32BT | 2026-11-08T04:58:18-08:00 |
| B2s_latency | 2026-11-08T06:05:19-08:00 |
| B2h0_prep | 2026-11-08T06:22:57-08:00 |
| B2h0_smoke_4BI | 2026-11-08T06:29:12-08:00 |
| B2h0_smoke_8BI | 2026-11-08T06:30:15-08:00 |
| B2h0_smoke_32BI | 2026-11-08T06:31:48-08:00 |
| B2h0_smoke_4BT | 2026-11-08T06:33:18-08:00 |
| B2h0_smoke_8BT | 2026-11-08T06:34:43-08:00 |
| B2h0_smoke_32BT | 2026-11-08T06:38:40-08:00 |
| B2h0_mv_4BI | 2026-11-08T06:40:05-08:00 |
| B2h0L_4BI | 2026-11-08T06:59:23-08:00 |
| B2h0L_8BI | 2026-11-08T07:27:28-08:00 |
| B2h0L_32BI | 2026-11-08T09:01:06-08:00 |
| B2h0L_4BT | 2026-11-08T11:20:23-08:00 |
| B2h0L_8BT | 2026-11-08T13:40:01-08:00 |
| B2h0L_32BT | 2026-11-08T21:31:33-08:00 |
| B2h0F_4BI | 2026-11-08T22:19:43-08:00 |
| B2h0F_8BI | 2026-11-08T23:30:46-08:00 |
| B2h0F_32BI | 2026-11-09T03:30:11-08:00 |
| B2h0F_4BT | pending |
| B2h0F_8BT | pending |
| B2h0F_32BT | pending |
| B2h_latency | pending |

## Latest progress lines

- `[07:52:10] B2 herbench 4BT main: 4000/5354`
- `[08:06:24] B2 herbench 4BT main: 4200/5354`
- `[08:22:00] B2 herbench 4BT main: 4400/5354`

## Latest stops / flags

- `[11:20:22] B2 herbench 4BT: 2071 ok, 0 still failed, frame-checked 2071`
- `[13:40:00] B2 herbench 8BT: 2071 ok, 0 still failed, frame-checked 2071`
- `[21:31:31] B2 herbench 32BT: 2071 ok, 0 still failed, frame-checked 2071`
- `[22:19:42] B2 herbench 4BI: 7425 ok, 0 still failed, frame-checked 0`
- `[23:30:44] B2 herbench 8BI: 7425 ok, 0 still failed, frame-checked 5354`
- `[03:30:09] B2 herbench 32BI: 7425 ok, 0 still failed, frame-checked 5354`

