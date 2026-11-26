# DEPLOYMENT CONDITION SPACE: SOURCED RANGES (2026-11-26T18:51Z). PROVISIONAL; research pass by an agent (READ = page or PDF text read in full or the relevant section; SNIP = search snippet only); the user decides which edges to test; every unsourced number is flagged. Companion to research/study_deployment_regime_program.md.
## (a) Uplink per robot
| edge | value | what it counts | source | status |
|---|---|---|---|---|
| low | 2.219 Mbps | Ookla 2026Q3 test-weighted p10 mobile upload, US bbox proxy | results/orchestration/live2/d234_uplink_tiers/d234_ookla_uplink_tiers.json (Ookla Open Data) | READ (repo JSON); single-user speedtests |
| typical | 13.6 Mbps (D75: T-Mobile median 5G upload, Ookla H2 2025); Ookla p50 18.416 | per-test median | links.py D75; same JSON | repo-committed; D75 source page not re-read |
| high | 60.86 Mbps | Ookla 2026Q3 p90 | same JSON | READ (repo JSON) |
| 5G field cross-check | median 12 Mbps Bay Area, RTT p90 142 ms | 80 T-Mobile tests, Jul 2022 to Jul 2023 | Khan et al., "How Mature is 5G Deployment? A Year-Long Study of 5G Uplink Performance", IFIP Networking 2024, pp. 276-284 | SNIP (extension Comput. Commun. 2025); the 12 Mbps is repo-quoted, not re-read |
| Wi-Fi lab ceiling | 231 / 459 / 918 Mbps UL at 20 / 40 / 80 MHz, phone 5 ft from router | PHY-near peak | IFIP Networking 2024 (dl.ifip.org 1571003562) | SNIP; a ceiling, not a per-robot rate |
| Wi-Fi office trial | Wi-Fi 6 about 0.31 Gbps UL, 40 MHz | vendor-backed trial, 2025 | WBA/AT&T/Intel/CommScope via RCR Wireless | SNIP, vendor |
| Wi-Fi shared | at 25 users per 80 MHz AP 20 percent throughput loss against 5 users (Wi-Fi 5: 80 percent loss at 15) | vendor pilot, Nov 2021 | Intel IT, "Wi-Fi 6: Real Advantages" | READ (PDF text) |
No citable per-robot Wi-Fi uplink percentile exists (cellular tiers for Wi-Fi robots only as a flagged proxy); speedtest rates are single-user, not cell-shared. 3GPP TS 22.104 V18.4.0 (2024-07) sets a REQUIREMENT, not a measurement: "Mobile robots, video streaming" UL above 10 Mbit/s, availability above 99.9999 percent, MTBF about 1 week (READ, clause 5). **5 Mbps: UNSOURCED.**
## (b) Outage duration
| edge | value | what it counts | source | status |
|---|---|---|---|---|
| low | 1 s (Irish 5G no-cell runs 1 to 3 s; n = 3,556 at 1 s) | cell absent | repo n2 json, e31b | repo-committed |
| typical | median 6 s; 70.8 percent under 30 s | per-DEVICE cellular failure (Data_Setup_Error, Data_Stall, Out_of_Service), Android, 70M users, 34 phone models, Jan to Aug 2020 | Li et al., "A Nationwide Study on Cellular Reliability", ACM SIGCOMM 2021 | READ (PDF) |
| mean | 188 s | same | same | READ |
| tail | over 80 percent of Data_Stall under 300 s; under 10 percent over 1,200 s; max 91,770 s (25.5 h); long ones "typically in remote regions" | same | same (sec 2 and 3.1) | READ; no p90 or p99 in the text (Fig. 4 is a CDF to 1,200 s); 94 percent of total failure DURATION is Data_Stall |
**Gaps:** (1) Li et al. is per-device, Android software stalls included, NOT a shared-cell or AP outage distribution; (2) Wi-Fi AP or site outage duration: NO citable distribution found (one search; a Ruckus survey of counts, self-reported, SNIP); (3) shared-cell outage (the STCO paper) could not be read; Iqbal et al. arXiv 2405.10787 (5G mobility simulation) gives tens of ms and does not bear on site outages. **Correlated or shared outage duration stays UNSOURCED;** the 188 s mean is a per-device figure applied to a group by assumption.
## (c) Memory per robot (model config READ: HF Qwen3-VL-32B-Instruct config.json text_config: 64 layers, 8 KV heads, head_dim 128, bfloat16): KV bytes per token = 2 (K,V) x 64 x 8 x 128 x 2 B = 262,144 B = **256 KiB per token** (assumes bf16 KV with no fp8 cache; the repo's engine KV dtype was NOT checked: FLAG)
| level | tokens | KV GiB |
|---|---|---|
| resident (committed, per robot) | 5,750 | 1.40 |
| history low / high | 17,000 / 26,000 | 4.15 / 6.35 |
| ask history p50 / max (repo) | 15k / 27k | 3.7 / 6.6 |
| committed 1x pool | 62,944 | 15.37 (about 11 robots at 5.75k) |
| halved pool | 31,472 | 7.69 (about 5.5 robots) |
GPU memory: weights about 65 GB bf16 (32.8B parameters x 2, the agent's arithmetic, not a source) leave about 28 GB of an H100 NVL 94 GB: **the 15.4 GiB pool is a utilisation-capped SETTING, not a hardware limit; sizing it from the card (about 28 GB, about 107k tokens) would be an uncommitted setting.** The 5.75k and 17k to 26k counts are committed repo measurements, not external sources.
## (d) Fleet size
| edge | value | what it counts | source | status |
|---|---|---|---|---|
| low | 11 robots per AP | the committed 3:11:2 cell | repo | committed, not a source |
| Wi-Fi capacity | Intel planning cap 15 users per AP; pilot supported 25 (Wi-Fi 6, 80 MHz); Wi-Fi 5 failed at 20 | laptop users, real office, 2021 | Intel IT paper | READ; vendor pilot, laptop clients, not robots |
| typical | 30 per AP (max 50) | AutoStore FAQ (vendor) | repo-quoted | vendor; read earlier |
| 3GPP | up to 50 UEs (mobile robots, 40 to 250 B messages) and up to 2,000 UEs (robot video) per 1 km2 service area | requirement tables | 3GPP TS 22.104 V18.4.0, Annex A / clause 5 | READ; requirements, not measurements |
| high | 40 to 500 per site (Locus), 1,000+ (Ocado) | whole site, not per AP | vendors | repo-quoted |
No peer-reviewed robots-per-AP or per-5G-cell measurement was found (two searches; trade text gives an unsourced 25 to 30 devices per AP rule, SNIP). **Robots per 5G cell: UNSOURCED.** Vendor AP data sheets (512 per radio) remain SNIP and are not robot ratios.
## UNSOURCED in the repo's committed scenarios
The committed d = 120 s outage (nearest sourced: Li mean 188 s, 70.8 percent under 30 s); 5 Mbps; robots per 5G cell; shared-cell or AP outage duration; a Wi-Fi outage distribution; per-robot Wi-Fi uplink. Not read: Khan et al. numbers, STCO, the AutoStore, Locus and Ocado pages (repo quotes), Zscaler.
## EDGES TO TEST (edges, not tuned points; all rates are single-user speedtest numbers: the shared-cell reading is an ASSUMPTION)
Uplink 2.219 (p10), 13.6 (typical), 60.86 (p90) Mbps. Outage 1 s, 6 s (Li median), 30 s (Li 70.8th percentile), 188 s (Li mean; per-device applied as correlated, flagged), about 1,200 s (Li: under 10 percent exceed; equals the run length, so the whole-run extreme). Memory 1.40 / 4.15 / 6.35 GiB per robot (5.75k, 17k, 26k tokens) against the 15.37 and 7.69 GiB pools. Fleet 11, 15 (Intel planning cap), 25 (Intel pilot), 30 (AutoStore typical), 50 (AutoStore max and the TS 22.104 UE count) robots per AP.
