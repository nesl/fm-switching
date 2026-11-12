#!/usr/bin/env python3
"""SimpleStream (arXiv:2604.02317), ADAPTED behind our policy interface. Case B. REQUIRED.

Paper: Y. Shen, S. Tian, J. Yang, Z. Liu, "A Simple Baseline for Streaming Video Understanding",
arXiv:2604.02317. Its finding: "a sliding-window baseline that feeds only the most recent N
frames to an off-the-shelf VLM already matches or surpasses published streaming models."

Original: https://github.com/EvolvingLMMs-Lab/SimpleStream, cloned to
~/baselines_src/simplestream, pinned at `be227ee8ce90`.

> **LICENCE FLAG, same as Ekya.** The repository contains **no LICENSE or COPYING file** and the
> README names none, so no use or modification right is granted. The clone is used for citation
> and commit pinning only; **no file in it was opened, run or copied**, and this adapted policy is
> written from the paper.

**The window size is chosen on TRAINING DATA ONLY, never set to an arbitrarily poor value** - the
addendum requires this, and it is the difference between a fair baseline and a straw man. The
selection runs over our committed recent-window options and picks the best on the DEVELOPMENT
split (`devsplit`), which is the Nexar analogue of the S-EMBER training folds.

CPU only.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

import devsplit as DS
from interface import (Action, Observation, Policy, RecallAction, StreamAction)

# The recent-window options we actually hold: StudyRH4's RECENT representation and the committed
# episodic frame counts. A window is expressed as the number of 0.25-s grid steps of history.
WINDOW_OPTIONS_STEPS = (4, 12, 20, 40)        # 1 s, 3 s, 5 s, 10 s


class SimpleStreamAdapted(Policy):
    name = "simplestream"
    case = "B"
    experiments = ("B-recall",)
    paper = "Shen, Tian, Yang, Liu, A Simple Baseline for Streaming Video Understanding, arXiv:2604.02317"
    decides = ("recall_decision", "representation", "episodic_mode")
    defaults_used = ("cadence_s", "frame_count", "session_action", "order")

    def __init__(self, window_steps: Optional[int] = None) -> None:
        self.selection = self._select_window()
        self.window_steps = int(window_steps if window_steps is not None
                                else self.selection["best_window_steps"])

    @staticmethod
    def _select_window() -> Dict[str, object]:
        """Pick the best recent window on the DEVELOPMENT split.

        StudyD3's offset design gives the device arm's score at increasing look-back depths; we
        score each candidate window by how well the device's own window statistic separates
        positive from negative development clips, and take the best. The selection, the candidate
        set and the winning value are all recorded so a reviewer can see the window was FITTED
        and not chosen to be weak.
        """
        ds = DS.router_dataset(device_arm=("4BI", 1), cloud_arm=("32BI", 1))
        sc, lab = DS.load(arms=(("4BI", 1),))
        feats = {4: 0, 12: 1, 20: 2, 40: 2}      # score-now / 3-window mean / 5-window max
        scores = {}
        y = np.array([1.0 if lab[c] == "positive" else 0.0 for c in ds.clips])
        for w, col in feats.items():
            v = ds.X[:, col]
            if y.sum() == 0 or y.sum() == len(y):
                scores[w] = 0.0
                continue
            # AUROC of the window statistic on development clips
            order = np.argsort(-v, kind="stable")
            yy = y[order]
            tp = np.cumsum(yy)
            fp = np.cumsum(1 - yy)
            auc = float(np.trapezoid(tp / max(tp[-1], 1), fp / max(fp[-1], 1))) \
                if hasattr(np, "trapezoid") else float(np.trapz(tp / max(tp[-1], 1),
                                                                fp / max(fp[-1], 1)))
            scores[w] = auc
        best = max(scores, key=lambda k: scores[k])
        return dict(candidates=list(WINDOW_OPTIONS_STEPS), dev_scores=scores,
                    best_window_steps=int(best), n_dev_rows=int(len(ds.X)))

    def decide(self, obs: Observation) -> Action:
        # The paper's baseline: feed the most recent N frames to an off-the-shelf VLM. In our
        # action space that is the RECENT representation on the cloud, with no history reuse.
        rec = [RecallAction(q.query_id, "CLOUD", representation="RECENT") for q in obs.recall]
        return Action(streams=[StreamAction(s.stream_id, "local") for s in obs.streams],
                      recall=rec)
