"""ai.py — the two AI edges of the pipeline. Everything else is deterministic (pipeline.py).

    qa_summary(profile)                      -> str | None
    briefing(scorecard_df, prior_df=None)    -> str | None

System prompts come from prompts/qa_system.md and prompts/briefing_system.md — never inline.
The API key is read from .env (python-dotenv). Any failure — missing key, network, API error,
empty response — returns None; the caller writes its deterministic outputs and an
"AI summary unavailable" note. The last failure reason is kept in `last_error` for display.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

import pipeline

MODEL = "claude-sonnet-5-5"          # current Sonnet (human's choice, 2026-11-02)
MAX_TOKENS = 1000                    # both outputs truncated at 800 on the 2026-11-03 run; 1000 is untested
PROMPTS_DIR = Path(__file__).with_name("prompts")
QA_PROMPT = PROMPTS_DIR / "qa_system.md"
BRIEFING_PROMPT = PROMPTS_DIR / "briefing_system.md"
NEAR_THRESHOLD_PTS = 3               # briefing prompt: "within 3 points of a tier or activation threshold"
SCORE_DROP_FLAG_PTS = 5              # briefing prompt: "score drops > 5 points"

last_error: str | None = None


def _compact(obj) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"), ensure_ascii=False)


def _call(system_file: Path, user_text: str) -> str | None:
    """One Messages API call. Returns the text, or None on any failure (missing key included)."""
    global last_error
    last_error = None
    try:
        load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            last_error = "ANTHROPIC_API_KEY not set (.env)"
            return None
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # Sonnet 5.5 thinks adaptively by default and would spend the small max_tokens budget on thinking
            # before writing any text; "between_tools" switches thinking off for a plain (no-tool) request.
            thinking={"type": "between_tools"},
            system=system_file.read_text(encoding="utf-8"),
            messages=[{"role": "user", "content": user_text}],
        )
        if response.stop_reason == "refusal":
            last_error = "model refused"
            return None
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            last_error = f"empty response (stop_reason={response.stop_reason}, blocks={[b.type for b in response.content]})"
            return None
        if response.stop_reason == "max_tokens":
            text += "\n\n_[truncated at max_tokens]_"
        return text
    except Exception as exc:  # the pipeline must never fail because the AI call did
        last_error = f"{type(exc).__name__}: {exc}"
        return None


# ----------------------------------------------------------------------------- QA
def qa_summary(profile: dict) -> str | None:
    """Severity-classified QA report with a VERDICT line, from the deterministic profile only."""
    payload = {"profile": profile, "expected_schema_columns": pipeline.EXPECTED_COLUMNS,
               "standing_exclusions": pipeline.EXCLUDED_COLUMNS}
    return _call(QA_PROMPT, "Data profile (JSON):\n" + _compact(payload))


# ----------------------------------------------------------------------------- briefing
def _briefing_payload(scorecard, prior, qa_note):
    """Compact, precomputed input: gate-passers' components, tier thresholds, deterministic flags, the diff."""
    comp = ["pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism", "selection_score"]
    passers = scorecard[scorecard["passes_gates"]].sort_values(["MARKET_NAME", "selection_score"], ascending=[True, False])
    rows = [{"market": r.MARKET_NAME, "dasher": r.DASHER, "tier": r.tier, "fraud_review": bool(r.fraud_review),
             **{c.replace("pts_", ""): round(float(getattr(r, c)), 1) for c in comp}} for r in passers.itertuples()]
    cutoffs = {}
    for market, size in pipeline.TIER1_SIZE.items():
        scores = passers.loc[passers["MARKET_NAME"] == market, "selection_score"].sort_values(ascending=False).tolist()
        cutoffs[market] = {"tier1_last_in": round(scores[size - 1], 1) if len(scores) >= size else None,
                           "tier2_first_out": round(scores[size], 1) if len(scores) > size else None,
                           "activation_floor": pipeline.ACTIVATION_FLOOR}
    near = []
    for r in rows:
        c = cutoffs[r["market"]]
        refs = [v for v in (c["tier1_last_in"], c["tier2_first_out"], c["activation_floor"]) if v is not None]
        close = [ref for ref in refs if abs(r["selection_score"] - ref) <= NEAR_THRESHOLD_PTS and r["selection_score"] != ref]
        if close:
            near.append({"market": r["market"], "dasher": r["dasher"], "score": r["selection_score"], "near": close})
    d = pipeline.diff(scorecard, prior)
    if prior is not None:
        pri = prior.set_index(pipeline.KEYS)
        for change in d["tier_changes"]:
            key = (change["market"], change["dasher"])
            cur = scorecard.set_index(pipeline.KEYS).loc[key]
            change["component_change"] = {c.replace("pts_", ""): round(float(cur[c]) - float(pri.loc[key, c]), 1)
                                          for c in comp[:-1] if c in pri.columns}
        d["score_drops_over_threshold"] = [m for m in d["score_movers"] if m["change"] < -SCORE_DROP_FLAG_PTS]
    return {"scorecard_gate_passers": rows, "tier_cutoffs": cutoffs, "near_threshold": near,
            "fraud_review": [r["dasher"] for r in rows if r["fraud_review"]],
            "diff_vs_prior": d, "qa_note": qa_note or "not in this run's data"}


def briefing(scorecard_df, prior_df=None, qa_note: str | None = None) -> str | None:
    """Weekly ops briefing. Tier changes are phrased as recommendations pending human approval (prompt rule)."""
    payload = _briefing_payload(scorecard_df, prior_df, qa_note)
    return _call(BRIEFING_PROMPT, "Briefing input (JSON, all numbers precomputed):\n" + _compact(payload))
