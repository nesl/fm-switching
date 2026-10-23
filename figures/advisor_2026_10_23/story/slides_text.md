# Advisor story deck — text-only slides (2026-10-23)

Every number below is taken from `story_numbers.md`, which computes it from the committed result files. Nothing here is typed in by hand.

## Slide 1 — Three questions

1. **Does the larger model help, and at what latency?**  
   Device (Jetson Orin) 4B/8B against cloud (H100) 32B, on the same questions.
2. **Do token-level signals tell us when to escalate?**  
   Can the device itself decide which questions to send up?
3. **What happens when many devices share the cloud?**  
   What limits how many warm sessions one GPU can hold.

## Slide 7 — Takeaways and next steps

### Takeaways

1. **The 32B cloud model helps, and it is faster.** On the Orin's S-EMBER block the cloud reaches 44.2% against 36.7% for the best on-device arm (8B-Thinking), and it answers in 4.3 s sequentially — against 59.2 s on the device. With the history already in GPU memory the cloud's TTFT is 0.38 s.
2. **Its value is model size *plus* history.** Where the recent window misses the evidence (n = 97), moving to the cloud's recent-window prompt is worth +8.2 pp and the full history a further +17.5 pp [+7.3, +28.3]. Where the window already covers it (n = 748), the history is worth -0.9 pp [-3.7, +1.7] — nothing.
3. **Device signals do not yet find where escalation helps.** The best thinking-trace signal reaches AUROC 0.62 [0.57, 0.67] for device correctness. Escalating the least-confident 20% of ERQA questions from 4B-Instruct gives 40.8% against 42.9% for a random 20%.
4. **Cloud *state*, not cloud compute, limits escalation.** Keeping histories in GPU memory alone, median warm escalation TTFT goes from 0.53 s at D=4 to 1,520 s at D=24. With 256 GiB of host memory behind the GPU the same D=24 is 0.81 s. Paging a history back from host memory costs 0.46 s against 2.44 s to rebuild it.
   Thinking is not a lever at either tier: Thinking − Instruct is +1.9 pp on-device and -5.7 pp in the cloud on S-EMBER, and +3.0 / +2.0 pp on ERQA, at 1.8× the device latency on the A6000 mirror and 2.2× on the Orin itself.

### Next steps

- **Trigger study on a held-out split**, including a cloud-side history check: the device asks, the cloud decides whether its own history adds anything before it spends a full 32B pass.
- **End-to-end evaluation with strong baselines**: always-local, always-cloud, random escalation at a matched rate, and an oracle bound, under one latency budget.
- **Mobility and network**: every latency here is local HTTP or TTFT with no network. Reachability and handover change which tier is even available.

### Asks

- **Which deadline regime should we design for?** The device answers in 17–59 s; a warm cloud answers in about 0.4 s plus network. Those are different products.
- **Are S-EMBER and ERQA enough?** S-EMBER carries the history mechanism; ERQA carries the signals. Neither is a robot-deployment workload.

