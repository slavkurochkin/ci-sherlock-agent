from dataclasses import dataclass


WEIGHTS = {
    "stability": 0.30,     # pass rate over recent runs
    "failure_rate": 0.25,  # inverse of failure rate
    "performance": 0.20,   # duration trend (stable or improving)
    "flakiness": 0.15,     # proportion of flaky tests
    "pipeline": 0.10,      # job-level pass rate
}

MIN_RUNS = 3  # minimum runs required to produce a score


@dataclass
class ScoreFactor:
    name: str
    score: float   # 0.0–1.0
    weight: float
    detail: str


@dataclass
class ReadinessScore:
    score: int              # 0–100
    factors: list[ScoreFactor]
    insufficient_data: bool = False


def compute_release_readiness(runs: list[dict], test_results: list[dict]) -> ReadinessScore:
    """
    Compute a release readiness score from recent run history.

    Args:
        runs: rows from `runs` table, newest first
        test_results: rows from `test_results` for those runs
    """
    if len(runs) < MIN_RUNS:
        return ReadinessScore(score=0, factors=[], insufficient_data=True)

    factors = [
        _stability_factor(runs),
        _failure_rate_factor(runs),
        _performance_factor(runs),
        _flakiness_factor(test_results),
        _pipeline_factor(runs),
    ]

    weighted = sum(f.score * f.weight for f in factors)
    return ReadinessScore(score=round(weighted * 100), factors=factors)


def _stability_factor(runs: list[dict]) -> ScoreFactor:
    total_tests = sum(r["total_tests"] for r in runs if r["total_tests"])
    passed_tests = sum(r["passed_tests"] for r in runs if r["passed_tests"])
    score = passed_tests / total_tests if total_tests else 0.0
    return ScoreFactor(
        name="Test stability",
        score=score,
        weight=WEIGHTS["stability"],
        detail=f"{passed_tests}/{total_tests} tests passed across {len(runs)} runs",
    )


def _failure_rate_factor(runs: list[dict]) -> ScoreFactor:
    failed_runs = sum(1 for r in runs if r["status"] == "failed")
    rate = failed_runs / len(runs)
    score = 1.0 - rate
    return ScoreFactor(
        name="Failure rate",
        score=score,
        weight=WEIGHTS["failure_rate"],
        detail=f"{failed_runs}/{len(runs)} runs had failures",
    )


def _performance_factor(runs: list[dict]) -> ScoreFactor:
    durations = [r["duration_ms"] for r in runs if r["duration_ms"]]
    if len(durations) < 2:
        return ScoreFactor(name="Performance trend", score=0.8, weight=WEIGHTS["performance"], detail="Insufficient data")

    # Compare first half avg vs second half avg (newer = first)
    mid = len(durations) // 2
    newer_avg = sum(durations[:mid]) / mid
    older_avg = sum(durations[mid:]) / (len(durations) - mid)

    if older_avg == 0:
        score = 0.8
        detail = "Insufficient baseline"
    else:
        ratio = newer_avg / older_avg
        # score 1.0 if faster or same, degrades linearly up to 2x slower
        score = max(0.0, 1.0 - max(0.0, ratio - 1.0))
        trend = "faster" if ratio < 0.95 else ("stable" if ratio < 1.10 else "slower")
        detail = f"Suite is {trend} ({ratio:.2f}x vs baseline)"

    return ScoreFactor(name="Performance trend", score=score, weight=WEIGHTS["performance"], detail=detail)


def _flakiness_factor(test_results: list[dict]) -> ScoreFactor:
    if not test_results:
        return ScoreFactor(name="Flakiness", score=1.0, weight=WEIGHTS["flakiness"], detail="No data")

    flaky = sum(1 for r in test_results if r["retry_count"] > 0)
    total = len(test_results)
    flaky_rate = flaky / total
    score = max(0.0, 1.0 - flaky_rate * 5)  # 20% flaky → score 0
    return ScoreFactor(
        name="Flakiness",
        score=score,
        weight=WEIGHTS["flakiness"],
        detail=f"{flaky}/{total} test runs had retries ({flaky_rate:.1%})",
    )


def _pipeline_factor(runs: list[dict]) -> ScoreFactor:
    passed_runs = sum(1 for r in runs if r["status"] == "passed")
    score = passed_runs / len(runs)
    return ScoreFactor(
        name="Pipeline health",
        score=score,
        weight=WEIGHTS["pipeline"],
        detail=f"{passed_runs}/{len(runs)} pipeline runs passed",
    )
