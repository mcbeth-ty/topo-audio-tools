"""Ambient Relational Study workspace; playback always uses frozen metadata."""

import json
import hashlib
import random
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit.components.v2 import component

import ambient_library as library
import ambient_study_store as store
import ambient_study_analysis as analysis
import ambient_study_neighborhood as neighborhood
from ambient_saved import reconstruct, render_library_rows
from ambient_playback import audio_url, playback_scope
from ambient_preview import preview_audio

_ASSETS = Path(__file__).with_name("ambient_frontend")
@lru_cache(maxsize=8)
def _registered_canvas(js, css):
    revision = hashlib.sha256((js+css).encode()).hexdigest()[:16]
    return component(f"ambient_relational_study_{revision}", html='<div class="study-root"></div>',
                     css=css, js=js)


def _canvas_component():
    # Read assets on reruns: an imported module must not pin an obsolete renderer.
    controller = (_ASSETS / "audition.js").read_text().split("export default function", 1)[0]
    return _registered_canvas(controller+(_ASSETS / "study_pathfinder.js").read_text()+(_ASSETS / "study.js").read_text(),
                              (_ASSETS / "study.css").read_text())


def notify(message):
    st.session_state["ambient_study_notice"] = str(message)


def open_session(identity):
    st.session_state["ambient_study_id"] = identity


def leave_session():
    st.session_state.pop("ambient_study_id", None)


def rename(identity, key):
    try: store.update_state(identity, name=st.session_state[key].strip())
    except (OSError, ValueError) as error: notify(error)


def change_scheduling(identity,key):
    try:store.update_state(identity,scheduling_mode=st.session_state[key])
    except (OSError,ValueError) as error:notify(error)


def change_view(identity, key):
    try: store.update_state(identity, view=st.session_state[key])
    except (OSError, ValueError) as error: notify(error)


def unlock(identity):
    try:
        store.reveal(identity)
        st.session_state[f"ambient_study_view_{identity}"] = "Explore"
    except (OSError, ValueError) as error: notify(error)


def sample_study_candidates(records,usage,count,only_unstudied,seed,locked_ids=(),favorites=False):
    if not 10<=count<=40:raise ValueError("Choose 10–40 stimuli.")
    eligible=sorted(r["saved_id"] for r in records if not only_unstudied or not usage.get(r["saved_id"],{}).get("studies"))
    locked=list(dict.fromkeys(i for i in locked_ids if i in eligible))
    if len(locked)>count:raise ValueError("Unlock stimuli before reducing the set below its locked count.")
    rng=random.Random(seed);remaining=[i for i in eligible if i not in locked]
    picked=[]
    if favorites:
        favorite_ids={r["saved_id"] for r in records if r.get("favorite",False)}
        pool=[i for i in remaining if i in favorite_ids]
        picked=rng.sample(pool,min(count-len(locked),len(pool)))
    rest=[i for i in remaining if i not in picked]
    return locked+picked+rng.sample(rest,min(count-len(locked)-len(picked),len(rest))),len(eligible)


def study_candidate_set(records,usage,count,only_unstudied,force=False,favorites=False):
    signature=(count,only_unstudied)
    current=st.session_state.get("ambient_study_candidate_set",{})
    eligible={r["saved_id"] for r in records if not only_unstudied or not usage.get(r["saved_id"],{}).get("studies")}
    locked=[i for i in current.get("locked_ids",[]) if i in eligible]
    if (force or favorites or current.get("controls")!=signature or not set(current.get("ids",[]))<=eligible
            or len(current.get("ids",[]))!=min(count,len(eligible))):
        seed=random.SystemRandom().getrandbits(64)
        ids,pool_size=sample_study_candidates(records,usage,count,only_unstudied,seed,locked,favorites)
        current={"ids":ids,"controls":signature,"seed":seed,"sampled_at":store.now(),"eligible_pool_size":pool_size,"locked_ids":locked,"method":"favorites_then_random" if favorites else "random_saved_stimuli"}
        st.session_state["ambient_study_candidate_set"]=current
    return current


def use_favorite_candidates():
    if len(st.session_state.get("ambient_study_candidate_set",{}).get("locked_ids",[]))>24:
        notify("Unlock some stimuli first: favorites fills a 24-stimulus set.")
        return
    st.session_state["ambient_study_candidate_count"]=24
    st.session_state["ambient_study_candidate_favorites"]=True


def manager(cached_audio):
    sessions, errors = store.list_sessions()
    for error in errors: st.warning(f"Unreadable session: {error}")
    if sessions:
        names = {s["session_id"]: f"{s['name']} · {s['created_at'][:10]} · {s['session_id'][:8]}" for s in sessions}
        chosen = st.selectbox("Existing sessions", list(names), format_func=names.get, key="ambient_study_session_choice")
        st.button("Open / Resume", key="ambient_study_open", on_click=open_session, args=(chosen,))
    with st.expander("Create a new study session", expanded=True):
        records, errors = library.list_saved()
        for name, error in errors: st.warning(f"Library entry {name}: {error}")
        usage,membership_errors=library.study_usage()
        for error in membership_errors:st.warning(f"Study membership: {error}")
        st.text_input("Session name",key="ambient_study_create_name")
        controls=st.columns([1,2,1,1],vertical_alignment="bottom")
        minimum=max(10,len(st.session_state.get("ambient_study_candidate_set",{}).get("locked_ids",[])))
        with controls[0]:count=st.number_input("Stimuli in set",min_value=minimum,max_value=40,value=max(24,minimum),step=1,key="ambient_study_candidate_count")
        with controls[1]:only_unstudied=st.checkbox("Only not-yet-studied stimuli",value=True,key="ambient_study_candidate_unstudied",
                                                  help="Excludes every stimulus already in a frozen study inventory, including studies with no submitted trials.")
        with controls[2]:regenerate=st.button("Randomize set",key="ambient_study_candidate_randomize")
        with controls[3]:st.button("Use favorites",key="ambient_study_candidate_use_favorites",on_click=use_favorite_candidates,
                                   help="Fill 24 slots with eligible favorites, sampling randomly if needed; fill remaining slots randomly. Locked stimuli stay in the set.")
        favorites=st.session_state.pop("ambient_study_candidate_favorites",False)
        current=study_candidate_set(records,usage,count,only_unstudied,force=regenerate,favorites=favorites)
        by_id={r["saved_id"]:r for r in records}
        current["ids"].sort(key=lambda identity:identity not in current.get("locked_ids",[]))
        chosen=[by_id[identity] for identity in current["ids"]]
        st.caption(f"{len(chosen)} / {count} selected · {current['eligible_pool_size']} eligible Saved stimuli · {len(current.get('locked_ids',[]))} locked · randomizing preserves locks")
        complete=len(chosen)==count
        if not complete:st.warning(f"Only {len(chosen)} eligible Saved stimuli are available. Reduce the set size or include previously studied stimuli.")
        with st.container(height=420,border=True,key="ambient_study_candidate_window"):
            preview=bool(st.session_state.get("ambient_study_candidate_preview",False))
            _,epoch=playback_scope([{"stimulus_id":r["saved_id"]} for r in chosen],"Study candidate selection",(preview,))
            def lock_candidate(identity,enabled):
                locks=current.setdefault("locked_ids",[])
                if enabled and identity not in locks:locks.append(identity)
                elif not enabled and identity in locks:locks.remove(identity)
                current["ids"].sort(key=lambda item:item not in locks)
            render_library_rows(chosen,usage,False,epoch,cached_audio,key="ambient_study_candidate_rows",read_only=True,
                                locked_ids=current.get("locked_ids",[]),on_lock=lock_candidate,
                                preview=preview,allow_tag_edit=True)
        with st.container(horizontal=True,horizontal_alignment="right",key="ambient_study_candidate_preview_bar"):
            st.toggle("5s preview",value=False,key="ambient_study_candidate_preview",
                      help="Audition the same material in 5 seconds; release/reverb tails may extend playback.")
        st.selectbox("Fixed feedback policy",["Exploratory","Feedback Hidden"],key="ambient_study_create_policy")
        st.caption("Create session freezes this exact set. Exploratory allows feedback and Explore; Feedback Hidden withholds them until an explicit end-of-collection reveal.")
        def create():
            if st.session_state.get("ambient_study_id"):return
            try:
                latest,errors=library.list_saved()
                available={r["saved_id"]:r for r in latest}
                latest_usage,latest_errors=library.study_usage()
                ids=current["ids"]
                if len(ids)!=count or any(i not in available for i in ids):raise ValueError("The candidate set is incomplete or has changed in the library. Randomize the set again.")
                if only_unstudied and (latest_errors or any(latest_usage.get(i,{}).get("studies") for i in ids)):
                    raise ValueError("Some candidates are already in a study, or membership could not be verified. Randomize the set again.")
                selection={"method":current.get("method","random_saved_stimuli"),"locked_saved_ids":list(current.get("locked_ids",[])),"requested_size":count,"only_unstudied":only_unstudied,
                           "seed":current["seed"],"sampled_at":current["sampled_at"],"eligible_pool_size":current["eligible_pool_size"],
                           "selected_saved_ids":list(ids)}
                identity=store.create_session(st.session_state["ambient_study_create_name"],
                                               [available[i] for i in ids],st.session_state["ambient_study_create_policy"],selection)
                store.ensure_pending(identity);open_session(identity)
            except (OSError,ValueError,KeyError) as error:notify(error)
        st.button("Create session",key="ambient_study_create_submit",on_click=create,
                  disabled=not complete or bool(only_unstudied and membership_errors))


def plot_positions(coordinates):
    import numpy as np
    ids = list(coordinates)
    points = np.array([coordinates[i] for i in ids])
    spread = np.ptp(points, axis=0)
    scale = min(820/max(spread[0],1e-9),420/max(spread[1],1e-9))
    center = (points.min(axis=0)+points.max(axis=0))/2
    points = (points-center)*scale + [500,300]
    return {i:{"x":float(p[0]/1000),"y":float(p[1]/600)} for i,p in zip(ids,points)}


def mount_canvas(identity, manifest, data, cached_audio, frozen=None):
    if data["kind"]=="explore":
        if st.session_state.get("ambient_study_local_context")!=data["context"] or "ambient_study_canvas" not in st.session_state:
            st.session_state.pop("ambient_study_selected_node",None)
    st.session_state["ambient_study_local_context"]=data["context"]
    inventory = {item["stimulus_id"]:item for item in manifest["inventory"]}
    cache = st.session_state.setdefault("ambient_study_audio", {})
    fast_preview=data["kind"]=="trial" and data.get("fast_preview",False)
    spatial=data["kind"]=="explore" and data.get("n_components",2)>=3
    playback_seconds=data.get("audio_seconds",15) if spatial else 5 if fast_preview else None
    if playback_seconds not in (None,5,15,30):raise ValueError("Invalid playback duration.")
    def audio_key(node):
        return f"{identity}:{node}"+(f":preview{playback_seconds}" if playback_seconds else "")
    items = []
    for number, node in enumerate(data["ids"],1):
        metadata = inventory[node]["metadata"]
        wav = cache.get(audio_key(node))
        items.append({"id":node,"number":number,"label":metadata["chord"]["display_label"],
                      "notes":"; ".join(", ".join(s["notes_names"])+" ["+", ".join(map(str,s["notes_midi"]))+"]" for s in metadata["states"]),
                      "url":audio_url(wav,f"study-{audio_key(node)}") if wav else None})
    def event():
        message = st.session_state.get("ambient_study_canvas",{}).get("event")
        if not isinstance(message,dict): return
        try:
            kind = message["kind"]
            if data["kind"]=="explore" and kind in ("play","select"):
                if message.get("context",data["context"])!=data["context"]:return
                node=message.get("id")
                if node is not None and node not in data["ids"]:raise ValueError("Unknown selected stimulus.")
                st.session_state["ambient_study_selected_node"]={"context":data["context"],"id":node}

            if kind == "explore_settings":
                if not spatial or message.get("context")!=data["context"]:
                    raise ValueError("Playback controls are only available in the current spatial Explore view.")
                if "audio_seconds" in message:
                    seconds=message["audio_seconds"]
                    if seconds not in (5,15,30):raise ValueError("Invalid playback duration.")
                    st.session_state[f"ambient_study_explore_playback_seconds_{identity}"]=seconds
                if "show_tags" in message:
                    if not isinstance(message["show_tags"],bool):raise ValueError("Invalid tag display setting.")
                    st.session_state[f"ambient_study_spatial_tags_{identity}"]=message["show_tags"]
                return
            if kind == "preview":
                if data["kind"]!="trial" or message.get("context")!=data["context"]:
                    raise ValueError("Preview can only be changed in the current arrangement.")
                if not isinstance(message.get("enabled"),bool):raise ValueError("Invalid preview setting.")
                store.update_pending(identity,message["snapshot"])
                st.session_state[f"ambient_study_arrange_preview_{identity}"]=message["enabled"]
                return
            if kind == "tag":
                if data["kind"] != "trial" or message.get("context") != data["context"]:
                    raise ValueError("Tags can only be edited in the current arrangement.")
                if message.get("id") not in data["ids"]: raise ValueError("Unknown stimulus.")
                store.update_pending(identity,message["snapshot"])
                store.set_stimulus_tag(identity,message["id"],message.get("text"))
                return
            if kind == "submit":
                store.submit(identity,message["snapshot"]);notify("Arrangement submitted.")
                return
            if kind == "exposure" and frozen is None:
                store.exposure(identity, "arrangement_feedback" if data["kind"] == "trial" else "explore_map", data["exposure_token"])
            if data["kind"] == "trial":
                store.update_pending(identity,message["snapshot"])
            if kind == "play":
                node = message["id"]
                if node not in data["ids"]: raise ValueError("This stimulus is not in the current view.")
                cache = st.session_state.setdefault("ambient_study_audio",{})
                key = audio_key(node)
                wav = cache.pop(key,None)
                if wav is None:
                    metadata=inventory[node]["metadata"]
                    wav=preview_audio(metadata,playback_seconds) if playback_seconds else reconstruct(metadata,cached_audio)
                cache[key] = wav
                while len(cache)>4: cache.pop(next(iter(cache)))
                st.session_state["ambient_study_play_request"] = {"id":node,"token":uuid4().hex}
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError) as error: notify(error)
    annotations=frozen["tags"] if frozen is not None else store.load_session(identity)[1].get("stimulus_tags",{})
    view_token=frozen["model_id"] if frozen is not None else store.load_session(identity)[1]["view_token"]
    data = {**data,"tags":annotations,"exposure_token": data["context"]+":"+view_token,
            "thresholds":manifest["settings"]["distance_thresholds"],
            "category_descriptions":manifest["settings"].get("category_descriptions",{}),
            "items":items,"play_request":st.session_state.pop("ambient_study_play_request",None)}
    def exposure():
        if frozen is not None:return
        try:
            store.exposure(identity,"arrangement_feedback" if data["kind"]=="trial" else "explore_map",data["exposure_token"])
        except (OSError,ValueError,KeyError) as error:notify(error)
    _canvas_component()(key="ambient_study_canvas",data=data,height="content",on_event_change=event,on_exposure_change=exposure)


def progress(summary, feedback, new_pairs=None):
    if new_pairs is not None:
        st.caption(f"Pair coverage: {summary['observed_pairs']} / {summary['possible_pairs']} · New pairs in this trial: {new_pairs} / 6")
    else:st.caption(f"{summary['completed_trials']} completed trials · {summary['observed_pairs']}/{summary['possible_pairs']} pairs "
               f"({summary['coverage']:.0%}) · {summary['unobserved_pairs']} unobserved · {summary['uncertain_responses']} unable-to-judge responses")
    with st.expander("Coverage and reliability diagnostics"):
        st.write("Coverage: unique pairs with at least one valid ordinal judgment.")
        st.write("Valid repetition counts (count → number of pairs):",summary["repetitions"])
        if feedback:
            disagreement = summary["repeated_pair_disagreement"]
            st.write("Repeatability: mean nonmodal response fraction among repeatedly judged pairs:",
                     round(disagreement,3) if disagreement is not None else "Not yet assessed — no repeated pairs.")
            st.caption("Quantity of evidence, repeatability, and embedding fit are separate diagnostics.")


def local_rows(rows,ids):
    names={0:"Unrelated",1:"Weak",2:"Moderate",3:"Strong"}
    return [{"Neighbor":f"{ids.index(p['neighbor_id'])+1} · {p['neighbor_id'][:8]}",
             "Judgment":names.get(p["relatedness"],p["status"]),"Valid n":p["valid_count"],
             "Uncertain n":p["uncertain_count"],"Distance / RMS":p["normalized_distance"],
             "Mutual @5":p.get("mutual_5",all(rank<=5 for rank in p["neighbor_ranks"].values())),
             "Evidence":"Conflicting repeats" if p["valid_count"]>1 and sum(v>0 for v in p["counts"])>1 else "Repeated" if p["valid_count"]>1 else "Single · provisional" if p["valid_count"] else "Unmeasured"} for p in rows]


def problem_rows(rows,ids):
    return [{"Pair":"–".join(str(ids.index(i)+1) for i in p["ids"]),"IDs":" / ".join(p["ids"]),
             "Category":p["status"],"Valid judgments":p["valid_count"],"Uncertain":p["uncertain_count"],
             "Counts [0,1,2,3]":str(p["counts"]),"Raw distance":p["distance"],"Normalized distance":p["normalized_distance"],
             "Endpoint neighbor ranks":str(p["neighbor_ranks"]),"Evidence":p["evidence"]} for p in rows]


def local_comparison(name,n,fit,evaluated):
    metrics=evaluated["metrics"]
    def fraction(metric,numerator,denominator):
        return " / ".join(f"{metrics[str(k)][metric]:.0%} ({metrics[str(k)][numerator]}/{metrics[str(k)][denominator]})" if metrics[str(k)][metric] is not None else "—" for k in (3,5))
    return {"Fit":f"{name} {n}D", "Positive precision":fraction("positive_precision","moderate_strong_count","observed_denominator"),
            "Strong recall":fraction("strong_recall","strong_recalled","strong_denominator"),
            "Mutual Strong recall":fraction("strong_mutual_recall","strong_mutual_recalled","strong_denominator"),
            "Unrelated rate":fraction("false_neighbor_rate","unrelated_count","observed_denominator"),
            "Unknown rate":fraction("unknown_neighbor_rate","unknown_count","neighbor_pair_count"),
            "Single / repeated @3; @5":"; ".join(f"{metrics[str(k)]['single_observation_pairs']} / {metrics[str(k)]['repeated_observation_pairs']}" for k in (3,5)),
            "Positive Spearman":evaluated["positive_diagnostics"].get("spearman_dissimilarity_distance"),
            "Start variation":fit["embedding"].get("initialization_rms_variation",0)*n**.5}


@st.cache_data(max_entries=24,show_spinner=False)
def _cached_neighborhood(ids,pairs,coordinates):
    return neighborhood.evaluate(ids,pairs,coordinates)


@st.cache_data(max_entries=24,show_spinner=False)
def _save_model_reasons(ids,pairs,settings):
    return analysis.sufficiency(ids,pairs,settings,3)[0]


@st.fragment
def _explore_canvas(identity,manifest,data,cached_audio,frozen,result):
    # Audio/selection events rerun this fragment, never the fitting/sidebar page.
    data={**data,"show_tags":bool(st.session_state.get(f"ambient_study_spatial_tags_{identity}",data["show_tags"])) if data["n_components"]>=3 else data["show_tags"],
          "audio_seconds":st.session_state.get(f"ambient_study_explore_playback_seconds_{identity}",data["audio_seconds"])}
    if notice:=st.session_state.pop("ambient_study_notice",None):st.warning(str(notice))
    mount_canvas(identity,manifest,data,cached_audio,frozen=frozen)
    if frozen is not None:return
    embedding=result["embedding"];summary=result["summary"]
    local=_cached_neighborhood([i["stimulus_id"] for i in manifest["inventory"]],summary["pairs"],embedding["coordinates"])
    with st.expander("Local Neighborhood Diagnostics"):
        st.caption("Provisional · nearest neighbors use fitted Euclidean distances, using all fitted coordinates (including the color dimension in 4D). Unknown is not Unrelated. One judgment does not establish reliability.")
        selected_node=st.session_state.get("ambient_study_selected_node",{})
        expected=data["context"]
        node=selected_node.get("id") if selected_node.get("context")==expected else None
        ids=[i["stimulus_id"] for i in manifest["inventory"]]
        if node in local["per_stimulus"]:
            st.markdown(f"**Stimulus {ids.index(node)+1} · {node[:8]} — nearest 5**")
            st.dataframe(local_rows(local["per_stimulus"][node]["nearest_5"],ids),hide_index=True,width="stretch")
            st.markdown("**Strongest recorded partners · up to 8, highest category then farthest within ties**")
            partners=local["per_stimulus"][node]["strongest_partners"]
            if partners:st.dataframe(local_rows(partners[:8],ids),hide_index=True,width="stretch")
            else:st.caption("No observed positive partners.")
        else:st.caption("Select a node in the map to inspect its nearest five neighbors and strongest recorded partners.")


def explore(identity, manifest, state, cached_audio, frozen=None):
    preferences=st.session_state.setdefault("ambient_study_explore_preferences",{})
    preference=preferences.setdefault(identity,{"model":"Affinity","dimensions":"4D" if frozen is not None else "2D","map_mode":"Relationships"})
    # Preserve an existing UI preference as Ordinal when upgrading from the baseline.
    preference.setdefault("model","Ordinal");preference.setdefault("map_mode","Relationships");preference.setdefault("color_mode","Joint 4D")
    keys={name:f"ambient_study_{name}_{identity}" for name in ("model","dimensions","map_mode","color_mode")}
    def remember():
        for name,key in keys.items():
            if key in st.session_state:preference[name]=st.session_state[key]
    with st.sidebar:
        st.subheader("ANALYSIS")
        model=st.radio("Model",["Ordinal","Affinity"],index=["Ordinal","Affinity"].index(preference["model"]),
                       key=keys["model"],on_change=remember)
        selected=st.radio("Dimensions",["2D","3D","4D"],index=["2D","3D","4D"].index(preference["dimensions"]),
                          horizontal=True,key=keys["dimensions"],on_change=remember)
        color_mode="Joint 4D"
        if selected=="4D":
            color_mode=st.radio("4D layout",["Joint 4D","3D first + color"],
                index=["Joint 4D","3D first + color"].index(preference["color_mode"]),key=keys["color_mode"],on_change=remember,
                help="Joint 4D optimizes all coordinates. 3D first + color freezes the optimized 3D positions and fits color only; it cannot bring spatially distant nodes closer.")
        map_mode=st.radio("Map mode",["Relationships","Evidence"],index=["Relationships","Evidence"].index(preference["map_mode"]),
                          key=keys["map_mode"],on_change=remember)
        if selected=="2D":
            show_tags=st.checkbox("Display tags",key=f"ambient_study_show_tags_{identity}",value=False)
        else:show_tags=bool(st.session_state.get(f"ambient_study_spatial_tags_{identity}",False))
        connection_level="None"
        show_reference_cube=False
        if selected in ("3D","4D"):
            show_reference_cube=st.checkbox("Show reference cube",value=False,
                key=f"ambient_study_reference_cube_{identity}_{selected}",
                help="Show the orientation cube and its subtle floor reflections.")
            connection_key=f"ambient_study_connection_level_{identity}"+("_4d" if selected=="4D" else "")
            if st.session_state.get(connection_key)=="All":st.session_state[connection_key]="Weak"
            connection_level=st.select_slider("Connections",["None","Strong","Moderate","Weak"],
                value="Weak",key=connection_key,
                help="Progressively include weaker observed relationships: Strong only, Moderate and stronger, then Weak and stronger. Selected-node connections remain available; unobserved pairs are not added.")
    preference.update(model=model,dimensions=selected,map_mode=map_mode)
    if selected=="4D":preference["color_mode"]=color_mode
    dimension=int(selected[0])
    if dimension==4 and color_mode=="3D first + color":
        from ambient_study_color import extend_color,analyze as analyze_color
        with st.spinner("Fitting color with 3D positions fixed…"):
            if frozen is not None:
                stored=frozen["fits"].get(f"{model}:3D+color")
                result={**stored,"summary":frozen["summary"]} if stored else extend_color(
                    {**frozen["fits"][f"{model}:3"],"summary":frozen["summary"]},model)
            else:result=analyze_color(identity,model)
    elif frozen is not None:
        result={**frozen["fits"][f"{model}:{dimension}"],"summary":frozen["summary"]}
    elif dimension==4:
        result=analysis.cached_result(identity,dimension,model)
        if result is None:
            with st.spinner("Fitting the four-dimensional embedding…"):
                result=analysis.analyze(identity,dimension,model)
    else:result=analysis.analyze(identity,dimension,model)
    summary,embedding=result["summary"],result["embedding"]
    unstable=embedding.get("initialization_rms_variation",0)>.25
    st.caption(f"{model} · {selected} · {map_mode} · {embedding['status']} · {summary['coverage']:.0%} pair coverage"+
               (" · layout unstable" if unstable else ""))
    if dimension==4:
        if color_mode=="3D first + color":
            st.caption("3D first + color · XYZ exactly matches the optimized 3D fit. Color adds residual separation with XYZ and the 3D disparity targets fixed. This conditional objective differs from Joint 4D; colors are not emotion categories.")
            if embedding.get("color_range",1)<1e-6:st.caption("No beneficial additional color separation found; the color coordinate is flat.")
        else:st.caption("4D fit · XYZ sets spatial position; the fourth coordinate sets node color. Close-looking nodes can differ along the color dimension. Brightness still indicates camera depth. Axis orientation is arbitrary; colors are not emotion categories.")
    if frozen is None:
        reasons=[] if dimension>=3 and "coordinates" in embedding else _save_model_reasons(
            [item["stimulus_id"] for item in manifest["inventory"]],summary["pairs"],
            analysis.effective_settings(manifest["settings"]["analysis"]))
        with st.popover("Save model",disabled=bool(reasons)):
            model_name=st.text_input("Model name",value=state["name"],max_chars=100,key=f"ambient_model_save_name_{identity}")
            st.caption("Freeze both models in 2D, 3D and both 4D layouts from the current observations. Saves JSON only; audio stays on demand.")
            if st.button("Save to Models",key=f"ambient_model_save_{identity}",disabled=not model_name.strip()):
                from ambient_models import save_model
                try:
                    with st.spinner("Freezing model variants…"):
                        snapshot=save_model(identity,model_name)
                    st.session_state["ambient_models_selected"]=snapshot["model_id"]
                    st.success(f"Saved {snapshot['name']} to Models.")
                    missing=[key for key,fit in snapshot["fits"].items() if "coordinates" not in fit["embedding"]]
                    if missing:st.warning("Insufficient evidence for these frozen variants: "+", ".join(missing))
                except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:st.error(str(error))
    if "coordinates" not in embedding:
        st.info("Insufficient evidence for this frozen variant. Choose another dimension/model." if frozen is not None else "Insufficient evidence for this embedding. See Analysis Diagnostics for details.")
    else:
        compact_pairs={k:{field:p[field] for field in ("ids","counts","valid_count","uncertain_count","relatedness","disagreement")}
                       for k,p in summary["pairs"].items()}
        _explore_canvas(identity,manifest,{"kind":"explore","context":f"study:{identity}:explore:{model}:{selected}:{result['input_hash']}",
                     "ids":[i["stimulus_id"] for i in manifest["inventory"]],"model":model,
                     "positions":plot_positions(embedding["coordinates"]) if dimension==2 else {i:{"x":.5,"y":.5} for i in embedding["coordinates"]},
                     "n_components":dimension,"world_positions":embedding["coordinates"] if dimension>=3 else None,
                     "pairs":compact_pairs,"evidence":map_mode=="Evidence","show_tags":show_tags,
                     "connection_level":connection_level,"show_reference_cube":show_reference_cube,
                     "audio_seconds":st.session_state.get(f"ambient_study_explore_playback_seconds_{identity}",15)},cached_audio,frozen,result)
    if frozen is not None:
        with st.expander("Frozen model details"):
            st.caption("Stored fits never change when source study observations or analysis code changes.")
            st.dataframe([{"Model":name,"Dimensions":f"{n}D","Status":frozen["fits"][f"{name}:{n}"]["embedding"]["status"]}
                          for name in ("Ordinal","Affinity") for n in (2,3,4)],hide_index=True,width="stretch")
            st.download_button("Download model JSON",json.dumps(frozen,ensure_ascii=False,indent=2),
                               file_name=f"ambient_model_{identity}.json",mime="application/json",key=f"ambient_model_download_{identity}",on_click="ignore")
        return
    local=None
    if "coordinates" in embedding:
        local=_cached_neighborhood([i["stimulus_id"] for i in manifest["inventory"]],summary["pairs"],embedding["coordinates"])
    with st.expander("Analysis Diagnostics"):
        if st.button("Calculate all model / dimension comparisons",key=f"ambient_study_compare_{identity}"):
            with st.spinner("Calculating cached comparisons…"):
                for name in ("Ordinal","Affinity"):
                    for n in (2,3,4):analysis.analyze(identity,n,name)
        comparisons=[];local_comparisons=[]
        for name in ("Ordinal","Affinity"):
            for n in (2,3,4):
                fit=analysis.cached_result(identity,n,name)
                if fit is None:
                    comparisons.append({"Model":name,"Dimensions":f"{n}D","Status":"Not fitted for current observations"});local_comparisons.append({"Fit":f"{name} {n}D","Status":"Not fitted"});continue
                if "coordinates" in fit["embedding"]:
                    evaluated=_cached_neighborhood([i["stimulus_id"] for i in manifest["inventory"]],fit["summary"]["pairs"],fit["embedding"]["coordinates"])
                    local_comparisons.append(local_comparison(name,n,fit,evaluated))
                else:local_comparisons.append({"Fit":f"{name} {n}D","Status":fit["embedding"]["status"]})
                e=fit["embedding"];d=e.get("diagnostics",{});positive=analysis.positive_diagnostics(fit);absence=e.get("absence_diagnostics",{})
                comparisons.append({"Model":name,"Dimensions":f"{n}D","Status":e["status"],
                    "Ordinal Stress-1 ↓":e.get("observed_stress1"),"Affinity objective ↓":e.get("objective"),
                    "All-pair Spearman ↑":d.get("spearman_dissimilarity_distance"),"All-pair violations ↓":d.get("order_violation_fraction"),
                    "Positive Spearman ↑":positive.get("spearman_dissimilarity_distance"),
                    "Positive violations ↓":positive.get("order_violation_fraction"),
                    "Zeros below margin ↓":absence.get("violation_fraction"),"Zero mean shortfall ↓":absence.get("mean_shortfall"),
                    "Start variation ↓":e.get("initialization_rms_variation",0)*n**.5 if "coordinates" in e else None,
                    "Converged":e.get("converged"),"Starts":e.get("starts")})
        st.markdown("**Local neighborhoods · @3 / @5**")
        st.dataframe(local_comparisons,hide_index=True,width="stretch")
        st.caption("Each aggregate counts an unordered pair once if either endpoint selects the other. Precision = Moderate/Strong ÷ observed neighbor pairs; Unrelated rate = category 0 ÷ observed neighbor pairs. Unknown rate = unmeasured ÷ all neighbor pairs. Strong recall = recalled ÷ all observed Strong pairs; mutual recall requires both directions. Counts and denominators are shown; repeated judgments are not duplicate pairs. Distance ties break by stable stimulus ID. All findings are in-sample and provisional.")
        if local:
            st.markdown("**Current fit · ranked discrepancies**")
            ids=[i["stimulus_id"] for i in manifest["inventory"]]
            for label,field in [("Strong pairs, farthest first","distant_strong"),("Unrelated pairs, closest first","close_unrelated"),("Unobserved pairs, closest first — not false neighbors","close_unknown")]:
                st.write(label)
                rows=local["problems"][field][:8]
                if rows:st.dataframe(problem_rows(rows,ids),hide_index=True,width="stretch")
                else:st.caption("None in recorded data.")
            st.write("Stimuli with poor @5 matches; unknowns remain separate")
            st.dataframe([{"Stimulus":ids.index(p["stimulus_id"])+1,**p} for p in local["problems"]["poor_stimuli"][:8]],hide_index=True,width="stretch")
            st.write("Positive-category distance summaries (weighted observed-distance RMS = 1)")
            st.dataframe([{"Category":k,**v} for k,v in local["positive_level_distances"].items()],hide_index=True,width="stretch")
            st.caption("A single judgment cannot establish repeatability or a contradiction. Only mixed repeated response distributions are flagged as conflicting. Long Strong or close Unrelated pairs are descriptive discrepancies, not proof that a different attraction term will generalize. Normalized distances are not calibrated psychological units.")
        st.markdown("**Existing fit diagnostics**")
        st.dataframe(comparisons,hide_index=True,width="stretch")
        st.caption("↓ Lower is better; ↑ higher is better. Stress-1 and the Affinity objective are different losses and must not be compared numerically. All-pair Spearman and ordering violations are common descriptive diagnostics; initialization spread is aligned RMS displacement per stimulus at observed-pair RMS distance 1. More flexible models or dimensions may fit these observations better without improving validity or generalization.")
        for reason in embedding.get("reasons",[]):st.write(reason)
        st.write("Coverage",{k:summary[k] for k in ("completed_trials","possible_pairs","observed_pairs","unobserved_pairs","coverage","repetitions","uncertain_responses","repeated_pair_disagreement")})
        st.write("Missing pairs have no loss or scale weight. Lines show recorded median judgments, not fitted distances. Proximity between unobserved pairs is not measured similarity. Graph sufficiency gates are heuristics, not proof of identifiability. Initialization spread is not response repeatability.")
        if summary["repeated_pair_disagreement"] is None:st.caption("Repeatability cannot yet be assessed: no pair has repeated judgments.")
        if unstable:st.write("Different optimization starts produce substantially different layouts; do not interpret a single arrangement as uniquely determined.")
        st.write("Both models use lower ordinal medians, secondary ties, and weights min(valid count, 3). The existing Ordinal spherical nonmetric objective and corrected Kruskal Stress-1 remain unchanged.")
        st.write("Affinity fits only positive (1–3) category ordering. Explicit zeros receive a squared-hinge minimum-separation penalty, with no target or penalty beyond that margin. The scale constraint is weighted observed-pair RMS distance = 1; positive isotonic disparities have fixed RMS 0.5. This prevents uniform expansion/collapse and anchors positive fit relative to the absence margin. These scale and margin choices are modeling assumptions, not validated psychological units.")
        st.caption("Default absence margin 1.0; penalty strength 2.0. Affinity minimizes (weighted positive squared residual + 2 × weighted zero shortfall squared) / total observed weight, using projected gradient and backtracking. Missing pairs remain missing; an explicit zero is never treated as missing. The mean-shortfall metric includes all observed zeros, including satisfied ones.")
        st.json({"model":model,"dimension":dimension,"analysis_settings":result["settings"],
                 "parameters":result.get("parameters"),"objective_components":embedding.get("objective_components"),
                 "absence_diagnostics":embedding.get("absence_diagnostics"),
                 "fitted_disparities":embedding.get("fitted_disparities",embedding.get("positive_disparity_by_relatedness",embedding.get("fitted_positive_disparities"))),
                 "positive_diagnostics":embedding.get("positive_diagnostics"),
                 "start_diagnostics":embedding.get("start_diagnostics")},expanded=False)
        st.markdown("**Individual pair observation history**")
        ids=[i["stimulus_id"] for i in manifest["inventory"]]
        labels={k:f"{ids.index(p['ids'][0])+1}–{ids.index(p['ids'][1])+1} · {p['valid_count']} valid · {p['uncertain_count']} uncertain" for k,p in summary["pairs"].items()}
        key=st.selectbox("Pair",list(labels),format_func=labels.get,key=f"ambient_study_pair_{identity}")
        pair=summary["pairs"][key]
        st.write("Response distribution [0,1,2,3]:",pair["counts"],"Lower median:",pair["relatedness"])
        if pair["history"]:st.dataframe(pair["history"],hide_index=True)
        else:st.caption("No completed observations.")


def render_study(cached_audio):
    st.subheader("Relational Study")
    if notice := st.session_state.pop("ambient_study_notice",None): st.toast(notice)
    identity = st.session_state.get("ambient_study_id")
    try:
        if not identity:
            manager(cached_audio); return
        manifest,state = store.load_session(identity)
        policy = manifest["feedback_policy"]
        allowed = policy=="Exploratory" or bool(state["revealed_at"])
        controls = st.columns([3,2,1,1])
        with controls[0]:
            st.markdown(f"**{state['name']}** · {identity[:8]}")
            st.caption(f"{len(manifest['inventory'])} frozen stimuli · {policy}"+(" · collection closed" if state["collection_closed"] else ""))
        with controls[1]:
            choices = ["Arrange","Explore"] if allowed else ["Arrange"]
            key = f"ambient_study_view_{identity}"
            st.radio("Session view",choices,index=choices.index(state["view"]),horizontal=True,
                     label_visibility="collapsed",key=key,on_change=change_view,args=(identity,key))
        with controls[2]:
            st.button("Leave",key="ambient_study_leave",on_click=leave_session)
        with controls[3]:
            with st.popover("Session"):
                namekey=f"ambient_study_name_{identity}"
                st.text_input("Name",value=state["name"],key=namekey,on_change=rename,args=(identity,namekey))
                if allowed:
                    st.download_button("Export Session",json.dumps(store.export_session(identity),ensure_ascii=False,indent=2),
                                       file_name=f"relational_study_{identity}.json",mime="application/json",key="ambient_study_export",on_click="ignore")
                else:
                    st.caption("Export is available after the explicit end-of-collection reveal, so prior responses cannot be exposed during hidden collection. Raw JSON files are already persisted locally.")
                if policy=="Feedback Hidden" and not state["revealed_at"]:
                    confirm=st.checkbox("End collection permanently and reveal feedback",key=f"ambient_study_reveal_confirm_{identity}")
                    st.button("Reveal / unlock",disabled=not confirm,on_click=unlock,args=(identity,),key="ambient_study_reveal")
        completed,errors=store.trials(identity)
        if errors:
            for error in errors: st.error(error)
            st.info("Raw files were retained. Repair them before scheduling or fitting.");return
        summary=store.summarize(manifest,completed)
        if state["view"]=="Explore":
            if not allowed: st.info("Explore is locked by the session's feedback policy.");return
            explore(identity,manifest,state,cached_audio);return
        scheduling_key=f"ambient_study_scheduling_{identity}"
        st.selectbox("Trial Scheduling",list(store.SCHEDULING_MODES),
                     index=store.SCHEDULING_MODES.index(state["scheduling_mode"]),key=scheduling_key,width=260,
                     on_change=change_scheduling,args=(identity,scheduling_key),
                     help="Keeps the current pending trial. Changes apply to the next trial. Coverage counts valid submitted judgments; Unable to judge remains unmeasured.")
        pending=store.ensure_pending(identity)
        if pending is None:
            st.info("Collection is closed after feedback reveal. Explore and export remain available.");return
        fast_preview=bool(st.session_state.get(f"ambient_study_arrange_preview_{identity}",False))
        progress(summary,allowed,store.new_pair_count(pending["stimulus_ids"],summary))
        if summary["unobserved_pairs"]==0:
            st.caption("First-pass coverage complete · new trials use Adaptive scheduling.")
        st.caption(f"Trial {pending['sequence']} · arrange by perceived emotional relationship; click to listen, drag to position. Complete all four interactions or confirm the arrangement before submitting. No measurement is recorded until submission.")
        observed,total=summary["observed_pairs"],summary["possible_pairs"]
        st.progress(observed/total if total else 0,
                    text=f"First-pass pair coverage · {observed} / {total} relationships · {summary['coverage']:.1%} · {total-observed} remaining")
        mount_canvas(identity,manifest,{"kind":"trial","context":f"study:{identity}:trial:{pending['trial_id']}",
                                       "ids":pending["presentation_order"],"positions":pending["positions"],
                                       "pending":pending,"feedback":allowed,"fast_preview":fast_preview},cached_audio)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
        st.error(f"Study workspace: {error}")
        if st.button("Return to session manager",key="ambient_study_recover"):
            leave_session();st.rerun()
