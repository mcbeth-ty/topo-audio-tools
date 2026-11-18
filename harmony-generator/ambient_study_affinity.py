"""Affinity interpretation of frozen ordinal observations; NumPy only.

Scale: weighted RMS distance over OBSERVED pairs is exactly one. Positive
isotonic disparities have fixed weighted RMS .5. Explicit zeros have a fixed
minimum margin, not a maximum target. Missing pairs enter neither loss nor scale.
Projected gradient with Armijo backtracking retracts onto the fixed-scale
ellipsoid; positive disparities are minimized exactly at every evaluation.
"""
import hashlib
import json
import math
import numpy as np
import ambient_study_analysis as ordinal
import ambient_study_store as store

MODEL = 'affinity-projected-ordinal-hinge-v1'
PARAMETERS = {'absence_margin':1.0,'lambda_absence':2.0,'positive_disparity_rms':.5}


def prepare(ids,pairs,parameters):
    observed=[p for p in pairs.values() if p['valid_count']]
    index={identity:i for i,identity in enumerate(ids)}
    a=np.array([index[p['ids'][0]] for p in observed],dtype=int)
    b=np.array([index[p['ids'][1]] for p in observed],dtype=int)
    weights=np.array([min(p['valid_count'],3) for p in observed],float)
    ranks=np.array([3-p['relatedness'] for p in observed])
    positive=ranks<3;absent=~positive
    groups=[np.flatnonzero(ranks==v) for v in sorted(set(ranks[positive]))]
    return dict(ids=ids,observed=observed,a=a,b=b,w=weights,total=weights.sum(),ranks=ranks,
                positive=positive,absent=absent,groups=groups,parameters=parameters)


def normalize(x,problem):
    x=x-x.mean(axis=0)
    d=np.linalg.norm(x[problem['a']]-x[problem['b']],axis=1)
    rms=np.sqrt(np.average(d*d,weights=problem['w']))
    if not np.isfinite(rms) or rms<1e-12:raise ValueError('Affinity coordinates collapsed.')
    return x/rms


def evaluate(x,problem):
    """Loss and analytic envelope gradient, prior to scale-tangent projection."""
    a,b,w=problem['a'],problem['b'],problem['w'];p=problem['parameters']
    difference=x[a]-x[b];d=np.linalg.norm(difference,axis=1)
    groups=problem['groups'];mass=np.array([w[g].sum() for g in groups])
    means=np.array([np.average(d[g],weights=w[g]) for g in groups])
    fitted=ordinal.pava(means,mass)
    rms=np.sqrt(np.average(fitted*fitted,weights=mass))
    if rms<1e-12:raise ValueError('Positive-affinity disparities collapsed.')
    fitted=fitted*p['positive_disparity_rms']/rms
    residual=np.zeros(len(d))
    for g,value in zip(groups,fitted):residual[g]=d[g]-value
    shortfall=np.zeros(len(d));shortfall[problem['absent']]=np.maximum(0,p['absence_margin']-d[problem['absent']])
    positive=float(np.sum(w*residual**2)/problem['total'])
    absence=float(p['lambda_absence']*np.sum(w*shortfall**2)/problem['total'])
    derivative=2*w*(residual-p['lambda_absence']*shortfall)/problem['total']
    force=(derivative/np.maximum(d,1e-12))[:,None]*difference
    gradient=np.zeros_like(x);np.add.at(gradient,a,force);np.add.at(gradient,b,-force)
    return positive+absence,gradient,dict(positive=positive,absence=absence),d,fitted


def fit_affinity(ids,pairs,settings,previous=None,n_components=2,parameters=None):
    if n_components not in (2,3,4):raise ValueError('Supported dimensions are 2, 3 and 4.')
    parameters={**PARAMETERS,**(parameters or {})}
    if any(not math.isfinite(v) or v<=0 for v in parameters.values()):raise ValueError('Affinity parameters must be positive and finite.')
    problem=prepare(ids,pairs,parameters)
    if not problem['positive'].any():raise ValueError('Affinity needs observed positive relationships; zeros alone do not identify affinity ordering.')
    if not ordinal.connected(ids,[p['ids'] for p in problem['observed']]):raise ValueError('Disconnected observations do not identify a global map.')
    solutions=[];a,b,w=problem['a'],problem['b'],problem['w']
    for start in range(settings['starts']):
        x=normalize(np.random.default_rng(settings['seed']+start).normal(size=(len(ids),n_components)),problem)
        initial=evaluate(x,problem)[0];converged=False;maximum_increase=0.
        for iteration in range(settings['max_iterations']):
            loss,gradient,components,d,disparities=evaluate(x,problem)
            normal=np.zeros_like(x);force=2*w[:,None]*(x[a]-x[b])/problem['total']
            np.add.at(normal,a,force);np.add.at(normal,b,-force)
            tangent=gradient-normal*np.sum(gradient*normal)/np.sum(normal*normal)
            norm=float(np.sum(tangent*tangent))
            if norm<1e-10:converged=True;break
            step=4.;accepted=False
            for _ in range(30):
                candidate=normalize(x-step*tangent,problem)
                new=evaluate(candidate,problem)[0]
                if new<=loss-1e-4*step*norm:
                    accepted=True;break
                step*=.5
            if not accepted:break
            maximum_increase=max(maximum_increase,new-loss)
            x=candidate
            if loss-new<=settings['tolerance'] and norm<1e-6:
                converged=True;break
        loss,gradient,components,d,disparities=evaluate(x,problem)
        if not np.isfinite(loss):continue
        solutions.append(dict(x=x,loss=loss,initial=initial,components=components,converged=converged,
                              iterations=iteration+1,seed=settings['seed']+start,maximum_increase=maximum_increase))
    if not solutions:raise ValueError('No finite Affinity solution.')
    solutions.sort(key=lambda s:s['loss']);best=solutions[0];points=best['x']
    variation=max((float(np.sqrt(np.mean((ordinal.align(s['x'],points)-points)**2))) for s in solutions[1:]),default=0)
    if previous and all(i in previous and len(previous[i])==n_components for i in ids):
        points=ordinal.align(points,np.array([previous[i] for i in ids]))
    loss,_,components,d,disparities=evaluate(points,problem)
    absent=problem['absent'];shortfall=np.maximum(0,parameters['absence_margin']-d[absent])
    positive=problem['positive'];positive_obs=[p for p in problem['observed'] if p['relatedness']>0]
    positive_diagnostics=ordinal.fit_diagnostics(ids,positive_obs,points,w[positive],problem['ranks'][positive])
    diagnostics=ordinal.fit_diagnostics(ids,problem['observed'],points,w,problem['ranks'])
    return dict(status='Provisional',model='Affinity',model_version=MODEL,n_components=n_components,
                coordinates={i:p.tolist() for i,p in zip(ids,points)},objective=loss,objective_components=components,
                parameters=parameters,positive_diagnostics=positive_diagnostics,diagnostics=diagnostics,
                absence_diagnostics=dict(pair_count=int(absent.sum()),violating_pairs=int((shortfall>1e-8).sum()),
                    violation_fraction=float(np.mean(shortfall>1e-8)) if len(shortfall) else None,
                    mean_shortfall=float(np.average(shortfall,weights=w[absent])) if len(shortfall) else None,
                    rms_shortfall=float(np.sqrt(np.average(shortfall**2,weights=w[absent]))) if len(shortfall) else None,
                    maximum_shortfall=float(shortfall.max()) if len(shortfall) else None),
                scale='weighted observed-pair RMS distance = 1; fixed positive disparity RMS',
                fitted_positive_disparities=disparities.tolist(),
                positive_disparity_by_relatedness={str(3-level):float(value) for level,value in zip(sorted(set(problem['ranks'][positive])),disparities)},
                initialization_rms_variation=variation,
                converged=best['converged'],iterations=best['iterations'],starts=len(solutions),
                start_diagnostics=[{k:v for k,v in s.items() if k not in ('x',)} for s in solutions],
                fit_warning='Affinity objective is not Stress-1. Lower in-sample loss does not establish psychological validity or reliability.')


def fingerprint(identity,requested,completed,n_components,parameters):
    return hashlib.sha256(json.dumps([identity,MODEL,ordinal.effective_settings(requested),completed,n_components,parameters],sort_keys=True).encode()).hexdigest()


def analyze(identity,n_components=2,parameters=None):
    if n_components not in (2,3,4):raise ValueError("Supported dimensions are 2, 3 and 4.")
    parameters={**PARAMETERS,**(parameters or {})}
    manifest,_=store.load_session(identity);completed,errors=store.trials(identity)
    requested=manifest['settings']['analysis'];settings=ordinal.effective_settings(requested)
    digest=fingerprint(identity,requested,completed,n_components,parameters)
    path=store.folder(identity)/f'analysis_affinity_{n_components}d.json';previous=None
    if path.exists():
        try:
            old=store.read(path)
            if old.get('input_hash')==digest:return old
            previous=old.get('embedding',{}).get('coordinates')
        except (OSError,ValueError,TypeError):pass
    summary=store.summarize(manifest,completed);ids=[i['stimulus_id'] for i in manifest['inventory']]
    reasons,degree=ordinal.sufficiency(ids,summary['pairs'],settings,n_components)
    if not any(p['valid_count'] and p['relatedness']>0 for p in summary['pairs'].values()):reasons.append('No positive-affinity observations are available.')
    if errors:reasons.append('Some trial files are unreadable; repair them before fitting.')
    embedding=dict(status='Insufficient data',reasons=reasons)
    if not reasons:
        try:embedding=fit_affinity(ids,summary['pairs'],settings,previous,n_components,parameters)
        except (ValueError,np.linalg.LinAlgError) as error:embedding=dict(status='Fit unavailable',reasons=[str(error)])
    result=dict(derived=True,model='Affinity',model_version=MODEL,session_id=identity,n_components=n_components,
                input_hash=digest,computed_at=store.now(),parameters=parameters,
                settings={**settings,'version':MODEL,'n_components':n_components},summary=summary,degree=degree,embedding=embedding)
    store.atomic(path,result);return result
