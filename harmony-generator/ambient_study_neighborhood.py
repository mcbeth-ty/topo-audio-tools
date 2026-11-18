"""Read-only Euclidean neighborhood evaluation; no fitting or parameter changes.

Aggregate neighbor pairs are the undirected UNION of directed kNN lists. Every
pair is counted once. Precision and false-neighbor rates divide by observed
union pairs; unknown rate divides by all union pairs. Recall divides by all
observed Strong pairs. Exact distance ties break by stable stimulus ID.
"""
from itertools import combinations
import numpy as np
from ambient_study_store import pair_key
from ambient_study_analysis import fit_diagnostics

VERSION='local-neighborhood-v1'


def evaluate(ids,pairs,coordinates,ks=(3,5)):
    if len(ids)!=len(set(ids)) or set(ids)!=set(coordinates):raise ValueError('Coordinates must match the unique session inventory.')
    x=np.array([coordinates[i] for i in ids],float)
    if x.ndim!=2 or x.shape[1] not in (2,3,4) or not np.all(np.isfinite(x)):raise ValueError('Finite 2D, 3D or 4D coordinates are required.')
    index={identity:i for i,identity in enumerate(ids)}
    for key,p in pairs.items():
        if key!=pair_key(*p['ids']) or not set(p['ids'])<=set(ids):raise ValueError('Noncanonical or unknown stimulus pair.')
    distances=np.linalg.norm(x[:,None,:]-x[None,:,:],axis=2)
    observed=[p for p in pairs.values() if p['valid_count']]
    raw=[distances[index[p['ids'][0]],index[p['ids'][1]]] for p in observed]
    weights=[min(p['valid_count'],3) for p in observed]
    rms=float(np.sqrt(np.average(np.square(raw),weights=weights))) if observed else 0.
    scale=rms if rms>1e-12 else None
    ordered={i:sorted((j for j in ids if i!=j),key=lambda j:(float(distances[index[i],index[j]]),j)) for i in ids}
    ranks={i:{j:rank+1 for rank,j in enumerate(neighbors)} for i,neighbors in ordered.items()}
    def pair_record(a,b):
        p=pairs.get(pair_key(a,b),{});count=p.get('valid_count',0);hist=p.get('counts',[0]*4)
        uncertain=p.get('uncertain_count',0);d=float(distances[index[a],index[b]])
        evidence=('Conflicting repeated judgments' if sum(v>0 for v in hist)>1 else 'Repeated judgments') if count>1 else 'Single judgment; reliability unknown' if count else 'Unmeasured ordinal relationship'
        return dict(ids=sorted((a,b)),relatedness=p.get('relatedness') if count else None,
                    status=str(p.get('relatedness')) if count else 'Unable-to-judge only' if uncertain else 'Unobserved',
                    valid_count=count,uncertain_count=uncertain,counts=list(hist),evidence=evidence,
                    distance=d,normalized_distance=d/scale if scale else None,
                    neighbor_ranks={a:ranks[a][b],b:ranks[b][a]})
    records={pair_key(a,b):pair_record(a,b) for a,b in combinations(ids,2)}
    strong={key for key,p in records.items() if p['valid_count'] and p['relatedness']==3}
    metrics={};neighbors={};per_stimulus={i:{} for i in ids}
    for k in ks:
        if type(k) is not int or k<1:raise ValueError('Neighbor counts must be positive integers.')
        effective=min(k,max(0,len(ids)-1));sets={i:set(ordered[i][:effective]) for i in ids};neighbors[str(k)]={i:ordered[i][:effective] for i in ids}
        union={pair_key(i,j) for i in ids for j in sets[i]}
        seen=[records[key] for key in sorted(union) if records[key]['valid_count']]
        positives=sum(p['relatedness']>=2 for p in seen);false=sum(p['relatedness']==0 for p in seen)
        recalled=len(strong&union)
        mutual=sum(all(b in sets[a] for a,b in (records[key]['ids'],records[key]['ids'][::-1])) for key in strong)
        metrics[str(k)]=dict(k=k,effective_k=effective,neighbor_pair_count=len(union),observed_denominator=len(seen),
            moderate_strong_count=positives,positive_precision=positives/len(seen) if seen else None,
            unrelated_count=false,false_neighbor_rate=false/len(seen) if seen else None,
            unknown_count=len(union)-len(seen),unknown_neighbor_rate=(len(union)-len(seen))/len(union) if union else None,
            strong_denominator=len(strong),strong_recalled=recalled,strong_recall=recalled/len(strong) if strong else None,
            strong_mutual_recalled=mutual,strong_mutual_recall=mutual/len(strong) if strong else None,
            single_observation_pairs=sum(p['valid_count']==1 for p in seen),repeated_observation_pairs=sum(p['valid_count']>1 for p in seen),
            conflicting_repeated_pairs=sum(p['valid_count']>1 and sum(v>0 for v in p['counts'])>1 for p in seen))
        for i in ids:
            rows=[records[pair_key(i,j)] for j in ordered[i][:effective]]
            known=[p for p in rows if p['valid_count']]
            own_strong=[p for p in records.values() if i in p['ids'] and p['valid_count'] and p['relatedness']==3]
            per_stimulus[i][str(k)]=dict(observed_count=len(known),unknown_count=len(rows)-len(known),
                unrelated_count=sum(p['relatedness']==0 for p in known),moderate_strong_count=sum(p['relatedness']>=2 for p in known),
                positive_precision=sum(p['relatedness']>=2 for p in known)/len(known) if known else None,
                missed_strong_count=sum(next(j for j in p['ids'] if j!=i) not in sets[i] for p in own_strong))
    local={}
    for i in ids:
        nearest=[]
        for j in ordered[i][:5]:
            p=records[pair_key(i,j)]
            nearest.append({**p,'neighbor_id':j,'rank':ranks[i][j],'mutual_5':ranks[j][i]<=min(5,len(ids)-1)})
        partners=[{**p,'neighbor_id':next(j for j in p['ids'] if j!=i)} for p in records.values() if i in p['ids'] and p['valid_count'] and p['relatedness']>=1]
        partners.sort(key=lambda p:(-p['relatedness'],-p['distance'],p['neighbor_id']))
        local[i]=dict(nearest_5=nearest,strongest_partners=partners,metrics=per_stimulus[i])
    positive=[p for p in observed if p['relatedness']>0]
    positive_diagnostics=fit_diagnostics(ids,positive,x,np.array([min(p['valid_count'],3) for p in positive]),np.array([3-p['relatedness'] for p in positive])) if positive and scale else {}
    level_distances={}
    for level in (1,2,3):
        values=[p for p in records.values() if p['valid_count'] and p['relatedness']==level]
        ds=[p['distance'] for p in values]
        level_distances[str(level)]=dict(pair_count=len(values),single_count=sum(p['valid_count']==1 for p in values),repeated_count=sum(p['valid_count']>1 for p in values),
             raw_median=float(np.median(ds)) if ds else None,normalized_median=float(np.median(ds)/scale) if ds and scale else None,
             normalized_min=min(ds)/scale if ds and scale else None,normalized_max=max(ds)/scale if ds and scale else None)
    fifth=str(5 if 5 in ks else max(ks))
    poor=sorted((dict(stimulus_id=i,**per_stimulus[i][fifth]) for i in ids if per_stimulus[i][fifth]['unrelated_count']+per_stimulus[i][fifth]['missed_strong_count']>0),key=lambda p:(-(p['unrelated_count']+p['missed_strong_count']),-p['unknown_count'],p['stimulus_id']))
    return dict(version=VERSION,n_components=int(x.shape[1]),normalization='weighted observed-pair RMS distance = 1; weights min(valid count,3)',
                observed_distance_rms=scale,normalization_warning=None if scale else 'Normalized distances unavailable: no nonzero observed distance RMS.',
                metrics=metrics,neighbors=neighbors,per_stimulus=local,positive_diagnostics=positive_diagnostics,positive_level_distances=level_distances,
                problems=dict(distant_strong=sorted((p for p in records.values() if p['relatedness']==3),key=lambda p:(-p['distance'],p['ids'])),
                    close_unrelated=sorted((p for p in records.values() if p['relatedness']==0),key=lambda p:(p['distance'],p['ids'])),
                    close_unknown=sorted((p for p in records.values() if not p['valid_count']),key=lambda p:(p['distance'],p['ids'])),
                    poor_stimuli=poor))
