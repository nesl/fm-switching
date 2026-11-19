# Per robot question: arrival, deadline, history tokens at arrival (trace cum_tokens), believed readiness at arrival
# (last residency-log row for the session before arrival, else "never built"), the arm's decisions on the question,
# the build requests released for the session in [arrival, deadline], piece sizes, answer time and outcome.
# Inputs: --slurpfile out outcomes, --slurpfile dec decisions, --slurpfile req requests, --slurpfile res residency,
#         --slurpfile tr trace (history records only).
($dec | map(select((.opportunity_ids|length)>0)) | map(. as $d | .opportunity_ids[] | {k:., d:$d})
   | group_by(.k) | map({key:.[0].k, value:[.[].d]}) | from_entries) as $byopp
| ($dec | map({key:.decision_id, value:.}) | from_entries) as $decid
| $out[] | select(.kind=="recall")
| . as $o
| ($o.t_opportunity) as $ta | ($ta + $o.deadline_s) as $dl
| ([$tr[] | select(.session_id==$o.session_id and .t <= $ta)] | last) as $h
| ([$res[] | select(.session_id==$o.session_id and .t < $ta)] | last) as $rs
| ($byopp[$o.opportunity_id] // []) as $ds
| ([$req[] | select(.session_id==$o.session_id and (.opportunity_id==null) and .t_submit >= $ta - 1e-6 and .t_submit <= $dl + 0.2)
     | {t_submit:(.t_submit*1000|round/1000), kind:($decid[.decision_id].kind), piece_tokens:($decid[.decision_id].piece_tokens),
        prompt_tokens, cached_tokens, t_done:(.t_done*1000|round/1000)}]) as $builds
| ([$req[] | select(.opportunity_id==$o.opportunity_id)] | first) as $rr
| {opp:$o.opportunity_id, device:$o.device_id, arrival:($ta*1000|round/1000), deadline:($dl*1000|round/1000),
   history_tokens:($h.cum_tokens // 0), readiness_at_arrival:(if $rs then $rs.believed_tier else "never built" end),
   decisions:($ds | group_by(.kind) | map({key:.[0].kind, value:{n:length, first_t:(map(.t)|min), last_t:(map(.t)|max)}}) | from_entries),
   builds:$builds,
   recall_request:(if $rr then {t_submit:($rr.t_submit*1000|round/1000), prompt_tokens:$rr.prompt_tokens, cached_tokens:$rr.cached_tokens, t_first_token:$rr.t_first_token} else null end),
   answer_t:$o.t_delivered, answer_after_s:(if $o.t_delivered then (($o.t_delivered-$ta)*1000|round/1000) else null end),
   outcome:(if $o.within_L then "cloud on time" elif $o.t_delivered then "cloud late" else "no cloud answer (device)" end)}
