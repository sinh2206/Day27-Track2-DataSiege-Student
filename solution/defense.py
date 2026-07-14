from api import Verdict
from statistics import median


MIN_HISTORY = 8
WINDOW = 32
Z_ALERT = 3.0
Z_LEARN = 2.5


def _error(result, pillar):
    return Verdict(False, 0.0, result["error"], pillar)


def _verdict(reasons, pillar):
    return Verdict(bool(reasons), 1.0 if reasons else 0.9,
                   "; ".join(reasons) or "within expected bounds", pillar)


def _adaptive(ctx, group, metrics):
    """Return robust outliers and learn only non-extreme observations."""
    store = ctx.state.setdefault("metric_history", {})
    alerts = []
    for name, (raw_value, direction) in metrics.items():
        value = float(raw_value)
        history = store.setdefault(f"{group}.{name}", [])
        z_score = None
        if len(history) >= MIN_HISTORY:
            center = median(history)
            mad = median(abs(item - center) for item in history)
            if mad > 1e-12:
                delta = abs(value - center) if direction == "both" else value - center
                z_score = delta / (1.4826 * mad)
                if z_score > Z_ALERT:
                    alerts.append(f"{name}:robust_z={z_score:.2f}")
        if z_score is None or z_score <= Z_LEARN:
            history.append(value)
            del history[:-WINDOW]
    return alerts


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    result = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in result:
        return _error(result, "checks")

    baseline = ctx.baseline
    null_rate = result["null_rate"]["customer_id"]
    reasons = []
    if not baseline["row_count_min"] <= result["row_count"] <= baseline["row_count_max"]:
        reasons.append("row_count")
    if null_rate > baseline["null_rate_max"]:
        reasons.append("null_rate")
    if not baseline["mean_amount_min"] <= result["mean_amount"] <= baseline["mean_amount_max"]:
        reasons.append("mean_amount")
    if result["staleness_min"] > baseline["staleness_min_max"]:
        reasons.append("staleness")

    if not reasons:
        reasons = _adaptive(ctx, "checks", {
            "row_count": (result["row_count"], "both"),
            "null_rate": (null_rate, "high"),
            "mean_amount": (result["mean_amount"], "both"),
            "std_amount": (result["std_amount"], "both"),
            "staleness": (result["staleness_min"], "high"),
        })
    return _verdict(reasons, "checks")


def check_contract_checkpoint(payload, ctx):
    result = ctx.tools.contract_diff(
        payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in result:
        return _error(result, "contracts")

    reasons = [f"contract:{item}" for item in result["violations"]]
    if result["freshness_delay_min"] > ctx.baseline["freshness_delay_max_min"]:
        reasons.append("freshness_delay")
    return _verdict(reasons, "contracts")


def check_lineage_run(payload, ctx):
    result = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in result:
        return _error(result, "lineage")

    reasons = []
    upstream = result["actual_upstream"]
    expected_upstream = payload.get("expected_upstream")
    if expected_upstream is not None:
        if set(expected_upstream) - set(upstream):
            reasons.append("missing_upstream")
    elif len(upstream) < 2:
        reasons.append("missing_upstream")

    downstream = result["actual_downstream_count"]
    expected_downstream = payload.get("expected_downstream_count")
    if ((expected_downstream is not None and downstream != expected_downstream)
            or (expected_downstream is None and downstream <= 0)):
        reasons.append("orphan_output")
    if result["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        reasons.append("runtime")
    if not reasons:
        reasons = _adaptive(ctx, "lineage", {
            "duration_ms": (result["duration_ms"], "high"),
        })
    return _verdict(reasons, "lineage")


def check_feature_materialization(payload, ctx):
    result = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in result:
        return _error(result, "ai_infra")

    shift = result["mean_shift_sigma"]
    reasons = ["feature_skew"] if shift > ctx.baseline["feature_mean_shift_sigma_max"] else []
    if not reasons:
        reasons = _adaptive(ctx, "feature", {
            "mean_shift_sigma": (shift, "high"),
        })
    return _verdict(reasons, "ai_infra")


def check_embedding_batch(payload, ctx):
    result = ctx.tools.embedding_drift(
        payload["corpus"], payload["chunk_batch_id"])
    if "error" in result:
        return _error(result, "ai_infra")

    reasons = []
    if result["centroid_shift"] > ctx.baseline["embedding_centroid_shift_max"]:
        reasons.append("embedding_drift")
    if result["avg_doc_age_days"] > ctx.baseline["corpus_avg_doc_age_days_max"]:
        reasons.append("corpus_staleness")
    if not reasons:
        reasons = _adaptive(ctx, "embedding", {
            "centroid_shift": (result["centroid_shift"], "high"),
            "doc_age": (result["avg_doc_age_days"], "high"),
        })
    return _verdict(reasons, "ai_infra")
