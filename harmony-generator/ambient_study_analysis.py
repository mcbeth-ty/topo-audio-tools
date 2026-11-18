"""Observed-pair ordinal MDS in NumPy, with conservative sufficiency gates.

Minimize sum(w_ij * (||x_i-x_j|| - disparity(rank_ij))**2) on OBSERVED
pairs only. Lower medians summarize ordinal votes. Secondary (tie-preserving) ties receive one
shared disparity. Four-group weighted PAVA fits monotone disparities; weighted
SMACOF updates coordinates with a missing-edge Laplacian (weight zero for
missing pairs). Distances/disparities have weighted RMS 1 to prevent collapse.
No category spacing is supplied as a psychological interval scale.
"""

from itertools import combinations
import hashlib
import json
import math

import numpy as np

import ambient_study_store as store

MODEL = "observed-weighted-nonmetric-smacof-v2"


def connected(ids, edges, removed=()):
    remaining = set(ids) - set(removed)
    if not remaining: return True
    reached = {next(iter(remaining))}
    while True:
        grown = reached | {b for a, b in edges if a in reached and b in remaining} | {a for a, b in edges if b in reached and a in remaining}
        if grown == reached: return reached == remaining
        reached = grown


def sufficiency(ids, pairs, settings, n_components=2):
    observed = [p for p in pairs.values() if p["valid_count"]]
    edges = [p["ids"] for p in observed]
    degree = {identity: sum(identity in edge for edge in edges) for identity in ids}
    required = max((n_components+1)*len(ids)-(n_components+1)*(n_components+2)//2,
                   math.ceil(settings["minimum_pair_coverage"] * len(pairs)))
    reasons = []
    if len(observed) < required: reasons.append(f"Need at least {required} distinct measured pairs; currently {len(observed)}.")
    if min(degree.values(), default=0) < max(settings["minimum_degree"],n_components+1):
        reasons.append(f"Each stimulus needs at least {max(settings['minimum_degree'],n_components+1)} measured neighbors.")
    if not connected(ids, edges): reasons.append("The observed-pair graph is disconnected.")
    elif any(not connected(ids, edges, removed) for size in range(1,n_components+1) for removed in combinations(ids, size)):
        reasons.append(f"The observed graph is too fragile: removing up to {n_components} nodes disconnects it.")
    if len({p["relatedness"] for p in observed}) < 2: reasons.append("At least two distinct ordinal categories are needed for relational contrast.")
    return reasons, degree


def pava(values, weights):
    blocks = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        blocks.append([index, index+1, float(value), float(weight)])
        while len(blocks) > 1 and blocks[-2][2] > blocks[-1][2]:
            right, left = blocks.pop(), blocks.pop()
            weight = left[3] + right[3]
            blocks.append([left[0], right[1], (left[2]*left[3]+right[2]*right[3])/weight, weight])
    output = np.empty(len(values))
    for start, end, value, _ in blocks: output[start:end] = value
    return output


def align(points, reference):
    points = points - points.mean(axis=0)
    reference = reference - reference.mean(axis=0)
    left, _, right = np.linalg.svd(points.T @ reference)
    return points @ (left @ right)


def fit_ordinal(ids, pairs, settings, previous=None, n_components=2):
    if n_components not in (2,3,4):
        raise ValueError("Supported embedding dimensions are 2, 3 and 4.")
    index = {identity: n for n, identity in enumerate(ids)}
    observed = [p for p in pairs.values() if p["valid_count"]]
    a = np.array([index[p["ids"][0]] for p in observed]); b = np.array([index[p["ids"][1]] for p in observed])
    ranks = np.array([3-p["relatedness"] for p in observed])
    weights = np.array([min(p["valid_count"], 3) for p in observed], dtype=float)
    levels = sorted(set(ranks)); groups = [np.flatnonzero(ranks == level) for level in levels]
    group_weights = np.array([weights[g].sum() for g in groups])
    laplacian = np.zeros((len(ids), len(ids)))
    for i, j, w in zip(a, b, weights):
        laplacian[i,i] += w; laplacian[j,j] += w; laplacian[i,j] -= w; laplacian[j,i] -= w
    if not connected(ids, [p["ids"] for p in observed]):
        raise ValueError("Disconnected observations do not identify a global map.")
    inverse = np.linalg.pinv(laplacian)
    def distances(x): return np.linalg.norm(x[a]-x[b], axis=1)
    def disparities(distance):
        means = [np.average(distance[g], weights=weights[g]) for g in groups]
        fitted = pava(means, group_weights)
        delta = np.zeros(len(distance))
        for g, value in zip(groups, fitted): delta[g] = value
        rms = np.sqrt(np.average(delta**2, weights=weights))
        if rms < 1e-12: raise ValueError("Ordinal disparities collapsed.")
        return delta / rms
    solutions = []
    for start in range(settings["starts"]):
        x = np.random.default_rng(settings["seed"] + start).normal(size=(len(ids),n_components))
        x -= x.mean(axis=0); x /= np.sqrt(np.average(distances(x)**2, weights=weights))
        last = float(np.average((distances(x)-disparities(distances(x)))**2, weights=weights))
        trace, converged = [last], False
        for iteration in range(settings["max_iterations"]):
            d = distances(x); delta = disparities(d)
            matrix = np.zeros_like(laplacian)
            for i,j,value in zip(a,b,weights*delta/np.maximum(d,1e-10)):
                matrix[i,j] -= value; matrix[j,i] -= value; matrix[i,i] += value; matrix[j,j] += value
            candidate = inverse @ matrix @ x
            rms = np.sqrt(np.average(distances(candidate)**2, weights=weights))
            if rms < 1e-12 or not np.all(np.isfinite(candidate)): raise ValueError("Degenerate/nonfinite coordinate update.")
            # Both distance and disparity norms are constrained. Normalizing V+BX
            # solves the spherical majorization step; it is not an accidental
            # rescaling of the unconstrained raw-stress SMACOF objective.
            candidate /= rms
            d = distances(candidate); delta = disparities(d)
            loss = float(np.average((d-delta)**2, weights=weights))
            if loss > last + 1e-10:
                raise ValueError("The majorization objective increased; no map is returned.")
            trace.append(loss)
            x = candidate
            if abs(last-loss) <= settings["tolerance"] * max(1, last if math.isfinite(last) else 1):
                converged = True; break
            last = loss
        solutions.append({"x": x, "start": start, "loss": loss, "converged": converged, "iterations": iteration+1,
                          "trace": trace,
                          "disparities": {str(level): float(np.average(delta[g], weights=weights[g])) for level,g in zip(levels,groups)}})
    solutions.sort(key=lambda s:s["loss"])
    best = solutions[0]
    if max(best["disparities"].values()) - min(best["disparities"].values()) < .025:
        raise ValueError("Fitted ordinal contrast collapsed; no interpretable map is available.")
    stability = [float(np.sqrt(np.mean((align(s["x"],best["x"])-best["x"])**2))) for s in solutions[1:]]
    points = best["x"]
    if previous and all(identity in previous and len(previous[identity])==n_components for identity in ids):
        points = align(points, np.array([previous[identity] for identity in ids]))
    # The optimized spherical loss is 2*(1-cosine). Conventional Kruskal
    # Stress-1 instead uses the least-squares isotonic disparities (optimal
    # dilation), giving sqrt(1-cosine**2). Both order solutions identically.
    def stress1(loss):
        cosine = float(np.clip(1-loss/2, 0, 1))
        return math.sqrt(max(0, 1-cosine*cosine))
    diagnostics = fit_diagnostics(ids, observed, points, weights, ranks)
    start_results = [{"seed": settings["seed"]+s["start"],
                      "stress1": stress1(s["loss"]), "spherical_stress": math.sqrt(s["loss"]),
                      "iterations": s["iterations"], "converged": s["converged"],
                      "initial_objective": s["trace"][0], "final_objective": s["trace"][-1],
                      "maximum_objective_increase": float(max(np.diff(s["trace"]), default=0))} for s in solutions]
    near = [s for s in solutions if stress1(s["loss"]) <= stress1(best["loss"])+.01]
    near_variation = max((float(np.sqrt(np.mean((align(s["x"],best["x"])-best["x"])**2))) for s in near), default=0)
    return {"status": "Provisional", "n_components": n_components, "coordinates": {identity: point.tolist() for identity,point in zip(ids,points)},
            "observed_stress1": stress1(best["loss"]),
            "stress_definition": "Kruskal Stress-1: sqrt(sum(w*(d-isotonic(d))**2)/sum(w*d**2)); secondary ties",
            "spherical_stress": math.sqrt(best["loss"]),
            "optimization_loss": best["loss"], "start_diagnostics": start_results,
            "diagnostics": diagnostics, "near_best_start_count": len(near),
            "near_best_rms_variation": near_variation, "converged": best["converged"],
            "iterations": best["iterations"], "starts": len(solutions),
            "initialization_rms_variation": max(stability, default=0),
            "fitted_disparities": best["disparities"],
            "fit_warning": "Observed-data fit is not reliability. Missing edges have zero weight; sparse/tied judgments can leave geometry unstable."}


def fit_diagnostics(ids, observed, points, weights, ranks):
    """Descriptive rank/order diagnostics, separate from the fitted objective."""
    index = {identity: i for i, identity in enumerate(ids)}
    distances = np.array([np.linalg.norm(points[index[p["ids"][0]]]-points[index[p["ids"][1]]]) for p in observed])
    distances /= np.sqrt(np.average(distances**2, weights=weights))
    def midranks(values):
        ordered = np.argsort(values, kind="stable"); result = np.empty(len(values))
        start = 0
        while start < len(values):
            end = start+1
            while end < len(values) and values[ordered[end]] == values[ordered[start]]: end += 1
            result[ordered[start:end]] = (start+end-1)/2
            start = end
        return result
    left, right = midranks(ranks), midranks(distances)
    rho = float(np.corrcoef(left,right)[0,1]) if np.std(left)>0 and np.std(right)>0 else None
    ordered = ranks[:,None] < ranks[None,:]
    violations = ordered & (distances[:,None] > distances[None,:]+1e-12)
    examples = sorted((dict(ids=p["ids"], valid_count=p["valid_count"], counts=p["counts"],
                            relatedness=p["relatedness"], dissimilarity_rank=int(rank),
                            normalized_distance=float(distance))
                       for p, rank, distance in zip(observed,ranks,distances) if p["relatedness"]==3),
                      key=lambda p:p["normalized_distance"],reverse=True)[:5]
    return {"distance_normalization": "weighted observed-pair RMS distance = 1",
            "spearman_dissimilarity_distance": rho, "spearman_weighting": "unweighted observed pair summaries; average ranks for ties",
            "cross_category_comparisons": int(ordered.sum()), "order_violations": int(violations.sum()),
            "order_violation_fraction": float(violations.sum()/ordered.sum()) if ordered.any() else None,
            "strong_pair_examples": examples}


def effective_settings(requested):
    # Model-v2 optimization policy. Frozen manifest settings remain historical;
    # the actual settings are exported with derived analysis, never written back.
    return {**requested, "version": MODEL, "starts": max(32,requested["starts"]),
            "max_iterations": max(1000,requested["max_iterations"]),
            "tolerance": min(1e-8,requested["tolerance"])}


def analyze(identity, n_components=2, model="Ordinal"):
    if model == "Affinity":
        from ambient_study_affinity import analyze as affinity_analyze
        return affinity_analyze(identity,n_components)
    if model != "Ordinal":raise ValueError("Unknown analysis model.")
    if n_components not in (2,3,4):
        raise ValueError("Supported embedding dimensions are 2, 3 and 4.")
    manifest, _ = store.load_session(identity)
    completed, errors = store.trials(identity)
    summary = store.summarize(manifest,completed)
    requested = manifest["settings"]["analysis"]
    settings = effective_settings(requested)
    # Preserve existing 2D/3D fingerprints and files; each dimension is independently cached.
    inputs = [MODEL,requested,completed] + ([n_components] if n_components!=2 else [])
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    path = store.folder(identity)/("analysis.json" if n_components==2 else f"analysis_{n_components}d.json")
    previous = None
    if path.exists():
        try:
            old = store.read(path)
            if old.get("input_hash") == digest: return old
            previous = old.get("embedding",{}).get("coordinates")
        except (OSError,ValueError,TypeError): pass
    ids = [item["stimulus_id"] for item in manifest["inventory"]]
    reasons, degree = sufficiency(ids,summary["pairs"],settings,n_components)
    if errors: reasons.append("Some trial files are unreadable; repair them before fitting.")
    embedding = {"status": "Insufficient data", "reasons": reasons}
    if not reasons:
        try: embedding = fit_ordinal(ids,summary["pairs"],settings,previous,n_components)
        except (ValueError,np.linalg.LinAlgError) as error: embedding = {"status":"Fit unavailable","reasons":[str(error)]}
    result = {"derived": True, "model_version": MODEL, "computed_at": store.now(), "input_hash": digest,
              "n_components": n_components, "settings": {**settings,"n_components":n_components}, "requested_settings": requested, "summary": summary, "degree": degree, "embedding": embedding}
    store.atomic(path,result)
    return result


def cached_result(identity,n_components=2,model="Ordinal"):
    """Read a current derived fit without triggering optimization."""
    manifest,_=store.load_session(identity);completed,errors=store.trials(identity)
    if errors:return None
    requested=manifest["settings"]["analysis"]
    if model=="Affinity":
        from ambient_study_affinity import fingerprint,PARAMETERS
        path=store.folder(identity)/f"analysis_affinity_{n_components}d.json"
        digest=fingerprint(identity,requested,completed,n_components,PARAMETERS)
    else:
        path=store.folder(identity)/("analysis.json" if n_components==2 else f"analysis_{n_components}d.json")
        digest=hashlib.sha256(json.dumps([MODEL,requested,completed]+([n_components] if n_components!=2 else []),sort_keys=True).encode()).hexdigest()
    try:
        result=store.read(path)
        return result if result.get("input_hash")==digest else None
    except (OSError,ValueError,TypeError):return None


def positive_diagnostics(result):
    """Common positive-only rank diagnostics without changing cached models."""
    e=result["embedding"]
    if "coordinates" not in e:return {}
    if "positive_diagnostics" in e:return e["positive_diagnostics"]
    observed=[p for p in result["summary"]["pairs"].values() if p["valid_count"] and p["relatedness"]>0]
    if not observed:return {}
    ids=list(e["coordinates"])
    return fit_diagnostics(ids,observed,np.array([e["coordinates"][i] for i in ids]),
                           np.array([min(p["valid_count"],3) for p in observed]),np.array([3-p["relatedness"] for p in observed]))
