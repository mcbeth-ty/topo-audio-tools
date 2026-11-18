"""Conditional fourth coordinate: freeze XYZ and fit remaining separation only."""
import copy
import hashlib
import json
import numpy as np
import streamlit as st
import ambient_study_analysis as ordinal

VERSION='fixed-xyz-residual-color-v1'
REGULARIZATION=1e-4


def fit_color(base,model):
    result={k:copy.deepcopy(v) for k,v in base.items() if k!='embedding'}
    result['n_components']=4
    result['settings']={**base['settings'],'n_components':4}
    result['model_version']=VERSION
    result['input_hash']=hashlib.sha256(json.dumps([VERSION,model,base['input_hash'],base['embedding']],sort_keys=True).encode()).hexdigest()
    original=base['embedding']
    if 'coordinates' not in original:
        result['embedding']={'status':original['status'],'reasons':original.get('reasons',[])}
        return result
    ids=list(original['coordinates']);xyz=np.array([original['coordinates'][i] for i in ids],float)
    if xyz.shape!=(len(ids),3) or not np.isfinite(xyz).all():raise ValueError('Color extension requires a finite 3D fit.')
    index={identity:n for n,identity in enumerate(ids)}
    observed=[p for p in base['summary']['pairs'].values() if p['valid_count']]
    a=np.array([index[p['ids'][0]] for p in observed]);b=np.array([index[p['ids'][1]] for p in observed])
    weights=np.array([min(p['valid_count'],3) for p in observed],float);total=weights.sum()
    squared=np.sum((xyz[a]-xyz[b])**2,axis=1)
    related=np.array([p['relatedness'] for p in observed]);positive=related>0
    if model=='Ordinal':
        targets=np.array([original['fitted_disparities'][str(3-value)] for value in related])
        active=np.ones(len(a),bool);absence_weight=0.;margin=0.
    elif model=='Affinity':
        targets=np.array([original['positive_disparity_by_relatedness'].get(str(value),0.) for value in related])
        active=positive;parameters=original['parameters']
        absence_weight=parameters['lambda_absence'];margin=parameters['absence_margin']
    else:raise ValueError('Unknown model.')
    def evaluate(w):
        difference=w[a]-w[b];distance=np.sqrt(squared+difference*difference)
        residual=np.where(active,distance-targets,0.)
        shortfall=np.where(~active,np.maximum(0,margin-distance),0.)
        loss=float(np.sum(weights*(residual**2+absence_weight*shortfall**2+REGULARIZATION*difference**2))/total)
        force=2*weights/total*((residual-absence_weight*shortfall)*difference/np.maximum(distance,1e-12)+REGULARIZATION*difference)
        gradient=np.zeros(len(ids));np.add.at(gradient,a,force);np.add.at(gradient,b,-force)
        return loss,gradient
    settings=base['settings'];seed=settings['seed'];starts=min(8,settings['starts'])
    zero=np.zeros(len(ids));baseline=evaluate(zero)[0];best=(baseline,zero,True,0)
    for start in range(starts):
        w=np.random.default_rng(seed+start).normal(0,.2,len(ids));w-=w.mean();loss,gradient=evaluate(w);converged=False
        for iteration in range(settings['max_iterations']):
            norm=float(gradient@gradient)
            if norm<1e-12:converged=True;break
            step=4.;accepted=False
            for _ in range(30):
                candidate=w-step*gradient;candidate-=candidate.mean();new,g=evaluate(candidate)
                if new<=loss-1e-4*step*norm:accepted=True;break
                step*=.5
            if not accepted:break
            change=loss-new;w,loss,gradient=candidate,new,g
            if change<settings['tolerance'] and norm<1e-6:converged=True;break
        if np.isfinite(loss) and loss<best[0]:best=(loss,w.copy(),converged,iteration+1)
    loss,w,converged,iterations=best
    if w[np.argmax(np.abs(w))]<0:w=-w
    coordinates={identity:[*original['coordinates'][identity],float(value)] for identity,value in zip(ids,w)}
    result['embedding']={'status':'Provisional','coordinates':coordinates,'n_components':4,
        'method':VERSION,'base_3d_input_hash':base['input_hash'],'objective':loss,'baseline_objective':baseline,
        'objective_definition':'Fixed 3D coordinates and fixed 3D fitted disparities; weighted residual separation loss plus original Affinity absence hinge and small W-difference regularization. No 4D RMS renormalization.',
        'regularization':REGULARIZATION,'seed':seed,'starts':starts,'iterations':iterations,'converged':converged,
        'color_range':float(np.ptp(w)),
        'fit_warning':'Conditional extension, not the joint 4D objective. Color can add separation but cannot bring points closer. Flat color is valid when no improvement is found. Color sign is arbitrary.'}
    return result


@st.cache_data(max_entries=24,show_spinner=False)
def _cached_color(serialized,model,version):
    return fit_color(json.loads(serialized),model)


def extend_color(base,model):
    return _cached_color(json.dumps(base,sort_keys=True),model,VERSION)


def analyze(identity,model):
    return extend_color(ordinal.analyze(identity,3,model),model)
