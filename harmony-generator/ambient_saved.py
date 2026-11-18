"""Saved Ambient UI and strict reconstruction from recorded pitches/settings."""

import copy
import json
from uuid import uuid4
import math
import hashlib
from pathlib import Path
from functools import lru_cache

import streamlit as st
from streamlit.components.v2 import component

import ambient_library as library
from ambient_audio import RENDERER_VERSION, SAMPLE_RATE, TRANSITION_SECONDS
from ambient_soundfont import (RENDERER_VERSION as SF_VERSION, REVERB_SETTINGS,
                               soundfont_identity)
from ambient_playback import playback_scope, render_player, audio_url


def reconstruct(metadata, cached_audio):
    library.validate_metadata(metadata)
    audio = metadata["rendering"]
    states = tuple(tuple(state["notes_midi"]) for state in metadata["states"])
    duration = audio["duration_seconds"]
    for index, state in enumerate(metadata["states"]):
        if (not math.isclose(state["start_seconds"], duration * index / len(states))
                or not math.isclose(state["end_seconds"], duration * (index + 1) / len(states))):
            raise ValueError("This saved transition timing is unsupported by the current renderer.")
    if not math.isclose(audio.get("transition_overlap_seconds", TRANSITION_SECONDS), TRANSITION_SECONDS):
        raise ValueError("The saved transition overlap differs from the current renderer.")
    version = SF_VERSION if audio["backend"] == "SoundFont" else RENDERER_VERSION
    if audio["renderer_version"] != version or audio["sample_rate"] != SAMPLE_RATE:
        raise ValueError("The saved renderer version/sample rate differs from the current renderer; audio was not substituted.")
    if audio["backend"] == "SoundFont":
        font = audio["soundfont"]
        identity = soundfont_identity(font["path"])
        if identity[1] != font["sha256"] or font["bank"] != 0:
            raise ValueError("The saved SoundFont identity/bank does not match. Restore the recorded SF2; no fallback was used.")
        if ("native_reverb_settings" in audio
                and audio["native_reverb_settings"] is not None
                and tuple(audio["native_reverb_settings"]) != REVERB_SETTINGS.get(audio["reverb"])):
            raise ValueError("The saved native reverb parameters differ from this renderer.")
        return cached_audio(states, duration, None, False, version, identity,
                            font["program"], audio["reverb"], audio["effect_level"])
    return cached_audio(states, duration, audio["timbre"], audio["reverb"], version)


def save_action(metadata):
    try:
        record, created = library.save_stimulus(metadata)
        st.session_state.setdefault("ambient_saved_tokens", set()).add(record["source_fingerprint"])
        st.session_state["ambient_save_notice"] = "Stimulus saved." if created else "This stimulus and rendering are already saved."
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        st.session_state["ambient_save_notice"] = f"Could not save stimulus: {error}"


def status_action(identity, status):
    try:
        library.set_status(identity, status)
    except (OSError, ValueError, KeyError) as error:
        st.session_state["ambient_save_notice"] = f"Could not update status: {error}"


def record_for(metadata):
    return st.session_state.get("ambient_collection_records", {}).get(metadata.get("stimulus_id"))


def bypass_action(metadata):
    record = record_for(metadata)
    try:
        if record:
            library.set_status(record["saved_id"],"bypassed",bypass_reasons=card_bypass_reasons(metadata))
        else:
            library.bypass_stimulus(metadata,card_bypass_reasons(metadata))
    except (OSError,ValueError,KeyError) as error:
        st.session_state["ambient_save_notice"]=f"Could not bypass stimulus: {error}"


def favorite_action(metadata, favorite, identity=None):
    try:
        record=record_for(metadata) if metadata else None
        if identity or record:
            library.set_favorite(identity or record["saved_id"],favorite)
        else:library.favorite_stimulus(metadata,favorite)
    except (OSError,ValueError,KeyError) as error:
        st.session_state["ambient_save_notice"]=f"Could not update favorite: {error}"


def close_detail():
    st.session_state.pop("ambient_detail", None)


def open_detail(metadata, index, wav=None, saved_id=None):
    st.session_state["ambient_detail"] = {"metadata": copy.deepcopy(metadata), "index": index,
                                          "wav": wav, "saved_id": saved_id}


def card_bypass_reasons(metadata):
    identity=metadata.get("stimulus_id") or library.fingerprint(metadata)
    return {reason:bool(st.session_state.get(f"ambient_bypass_reason_{identity}_{reason}",False)) for reason in library.BYPASS_REASON_KEYS}


def bypass_reason_changed(metadata):
    record=record_for(metadata)
    if record and record["status"]=="bypassed":bypass_action(metadata)


def save_control(metadata, index, wav=None, details=True, card_reasons=False, epoch=None):
    token = library.fingerprint(metadata)
    record = record_for(metadata)
    saved = record["status"] == "saved" if record else token in st.session_state.get("ambient_saved_tokens", set())
    columns = st.columns([.9,1,2.5,.45,.5] if card_reasons else ((3 if record else 2) if details else (2 if record else 1)),gap="small",vertical_alignment="bottom")
    with columns[0]:
        st.button("Saved ✓" if saved else "Save", key=f"ambient_save_{index}",
                  disabled=saved, on_click=save_action, args=(metadata,))
    if record or card_reasons:
        with columns[1]:
            bypassed=bool(record and record["status"]=="bypassed")
            st.button("Bypassed ✓" if bypassed else "Bypass",
                      key=f"ambient_bypass_{index}", disabled=bypassed,
                      on_click=bypass_action, args=(metadata,))
        if card_reasons:
            identity=metadata.get("stimulus_id") or token
            with columns[2],st.container(key=f"ambient_bypass_reason_fields_{identity}"):
                for reason,label in zip(library.BYPASS_REASON_KEYS,["incoherent or multi-emotional","overly unpleasant"]):
                    key=f"ambient_bypass_reason_{identity}_{reason}"
                    st.checkbox(label,value=(record or {}).get("bypass_reasons",{}).get(reason,False),key=key,
                                on_change=bypass_reason_changed,args=(metadata,))
    if card_reasons:
        from ambient_preview import render_preview_control
        with columns[3],st.container(key=f"ambient_card_preview_{metadata.get('stimulus_id') or token}"):
            render_preview_control(metadata,index,token,epoch)
        with columns[-1],st.container(key=f"ambient_card_favorite_{metadata.get('stimulus_id') or token}"):
            favorite=bool(record and record.get("favorite",False))
            st.button("★" if favorite else "☆",key=f"ambient_favorite_{index}",type="tertiary",
                      help="Remove favorite" if favorite else "Mark favorite",on_click=favorite_action,args=(metadata,not favorite))
    if details:
        with columns[-1]:
            st.button("Details", key=f"ambient_details_{index}", on_click=open_detail,
                      args=(metadata, index, wav, record["saved_id"] if record else None))


def delete_control(identity):
    key = f"ambient_confirm_delete_{identity}"
    if st.button("Delete", key=f"ambient_delete_{identity}"):
        st.session_state[key] = True
    if st.session_state.get(key):
        st.caption("Delete this saved record? The generated batch will be kept.")
        if st.button("Confirm delete", key=f"ambient_delete_yes_{identity}"):
            try:
                library.delete_saved(identity)
                st.session_state.pop(key, None)
                st.session_state.pop("ambient_saved_audition", None)
                st.rerun()
            except (OSError, ValueError) as error:
                st.error(f"Could not delete entry: {error}")
        if st.button("Cancel", key=f"ambient_delete_no_{identity}"):
            st.session_state.pop(key, None)
            st.rerun()


def select_saved(identity):
    st.session_state["ambient_saved_audition"] = identity
    st.session_state["ambient_library_play_request"] = uuid4().hex


def notes_action(identity, key):
    try:
        library.set_notes(identity, st.session_state[key])
    except (OSError, ValueError, KeyError) as error:
        st.session_state["ambient_save_notice"] = f"Could not save notes: {error}"


_tag_field = component("ambient_library_inline_tag",html='<input class="library-tag" type="text" maxlength="64" placeholder="Add tag…" aria-label="Stimulus tag (64 characters maximum)">',
    js="""export default function({parentElement,data,setTriggerValue}){
      const input=parentElement.querySelector('input');
      if(!input.matches(':focus'))input.value=data.value;
      input.title=input.value||'Add tag · 64 characters';
      input.oninput=()=>{input.title=input.value||'Add tag · 64 characters';};
      input.onchange=()=>setTriggerValue('tag',{id:data.id,value:input.value,token:crypto.randomUUID()});
      input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();input.blur();}};
    }""",
    css=""".library-tag{box-sizing:border-box;width:100%;height:26px;min-width:0;background:transparent;color:#aaa;border:1px solid #333;border-radius:3px;font:11px ui-monospace,monospace;padding:2px 6px;text-overflow:ellipsis;outline:none}.library-tag:focus{border-color:#888;color:#ddd}.library-tag::placeholder{color:#555}""")


def render_tag_field(identity, value):
    key=f"ambient_library_tag_{identity}"
    def changed():
        message=st.session_state.get(key,{}).get("tag")
        if not isinstance(message,dict) or message.get("id")!=identity:return
        try: library.set_tag(identity,message["value"])
        except (OSError,ValueError,KeyError) as error:st.session_state["ambient_save_notice"]=f"Could not save tag: {error}"
    _tag_field(key=key,data={"id":identity,"value":value},height=26,on_tag_change=changed)


_status_filter = component("ambient_library_status_filter",html='<div class="status-filter"></div>',
    js="""export default function({parentElement,data,setTriggerValue}){
      const root=parentElement.querySelector('.status-filter');
      let choice=data.choice,excluded=new Set(data.excluded);
      const button=(text,label)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.setAttribute('aria-label',label);return b;};
      const render=()=>{
        const opened=root.querySelector('details')?.open??root.__open??false;
        root.replaceChildren();const details=document.createElement('details'),summary=document.createElement('summary');
        details.open=opened;details.ontoggle=()=>{root.__open=details.open;};
        summary.textContent=choice+(excluded.size?' · − '+[...excluded].join(', '):'');details.append(summary);
        const menu=document.createElement('div');menu.className='status-options';
        const send=()=>{render();setTriggerValue('selection',{choice,excluded:[...excluded],token:crypto.randomUUID()});};
        for(const status of ['All','Saved','Unreviewed','Bypassed']){
          const row=document.createElement('div');row.className='status-option';
          const select=button(status,'Show '+status);select.className='status-choice';select.setAttribute('aria-pressed',String(choice===status));
          if(excluded.has(status))select.classList.add('excluded');
          select.onclick=()=>{choice=status;send();};row.append(select);
          const minus=button(status==='All'?'↺':'−',status==='All'?'Clear status exclusions':'Exclude '+status);
          minus.className='status-minus';minus.title=status==='All'?'Clear exclusions':excluded.has(status)?'Include '+status+' again':'Exclude '+status;
          minus.setAttribute('aria-pressed',String(status!=='All'&&excluded.has(status)));
          minus.disabled=status==='All'&&!excluded.size;
          minus.onclick=()=>{if(status==='All')excluded.clear();else if(excluded.has(status))excluded.delete(status);else excluded.add(status);send();};
          row.append(minus);menu.append(row);
        }
        details.append(menu);root.append(details);
      };render();
    }""",
    css=""".status-filter{font:11px ui-monospace,monospace;color:#ccc}
summary{cursor:pointer;border:1px solid #444;border-radius:4px;padding:9px;background:#171717;overflow-wrap:anywhere}.status-options{border:1px solid #444;border-radius:4px;padding:3px;margin-top:3px;background:#171717}.status-option{display:flex;align-items:center;gap:4px}button{font:inherit;color:#bbb;background:transparent;border:0;cursor:pointer;min-height:27px}button:hover{background:#292929}button:focus-visible,summary:focus-visible{outline:1px solid #aaa}.status-choice{flex:1;text-align:left;padding:3px 7px}.status-choice[aria-pressed=true]{color:#fff}.status-choice.excluded{text-decoration:line-through;color:#666}.status-minus{flex:0 0 26px;font-size:15px}.status-minus[aria-pressed=true]{background:#383838;color:#fff}.status-minus:disabled{opacity:.25;cursor:default}""")


def render_status_filter():
    options=("All","Saved","Unreviewed","Bypassed")
    choice=st.session_state.get("ambient_saved_status_filter","All")
    if choice not in options:choice="All"
    excluded=[s for s in st.session_state.get("ambient_saved_status_excluded",[]) if s in options[1:]]
    def changed():
        message=st.session_state.get("ambient_saved_status_selector",{}).get("selection")
        if not isinstance(message,dict) or message.get("choice") not in options:return
        negative=message.get("excluded")
        if not isinstance(negative,list) or any(s not in options[1:] for s in negative):return
        st.session_state["ambient_saved_status_filter"]=message["choice"]
        st.session_state["ambient_saved_status_excluded"]=list(dict.fromkeys(negative))
    st.caption("Status")
    _status_filter(key="ambient_saved_status_selector",data={"choice":choice,"excluded":excluded},height="content",on_selection_change=changed)
    return choice,{s.lower() for s in excluded}


def saved_page(records,page,page_size):
    if page_size not in (25,50,100):raise ValueError("Choose 25, 50 or 100 rows per page.")
    pages=max(1,(len(records)+page_size-1)//page_size)
    page=max(1,min(page or 1,pages))
    return records[(page-1)*page_size:page*page_size],page,pages


def change_saved_page(delta,pages):
    st.session_state["ambient_saved_page"]=max(1,min(pages,st.session_state.get("ambient_saved_page",1)+delta))


def render_saved(cached_audio, render_details):
    st.subheader("Stimulus Library")
    try:
        for note in library.migrate_legacy(): st.warning(note)
        records, errors = library.list_records()
        usage, study_errors = library.study_usage()
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Could not read the local library: {error}");return
    with st.sidebar:
        st.subheader("LIBRARY")
        choice,excluded_statuses=render_status_filter()
        study_filter=st.selectbox("Study participation",["All","Not in a study","In a study","No submitted trials","Has submitted trials"],key="ambient_saved_study_filter")
        maximum=max((len(item["studies"]) for item in usage.values()),default=0)
        counts=st.multiselect("Number of studies",list(range(maximum+1)),key="ambient_saved_study_counts",help="Leave empty to show every study count.")
        page_size=st.selectbox("Rows per page",[25,50,100],index=1,key="ambient_saved_page_size")
        st.caption("Audio renders only when you click Play. Tags save on Enter or blur.")
        st.download_button("Export Collection",json.dumps(library.export_collection(),ensure_ascii=False,indent=2),
                           file_name="hsg_ambient_collection.json",mime="application/json",key="ambient_collection_export",on_click="ignore")
    visible=[]
    for record in records:
        participation=usage.get(record["saved_id"],{"studies":[],"trials":0,"tags":[]})
        n=len(participation["studies"])
        if record["status"] in excluded_statuses:continue
        if choice!="All" and record["status"]!=choice.lower():continue
        if counts and n not in counts:continue
        if study_filter=="Not in a study" and n:continue
        if study_filter=="In a study" and not n:continue
        if study_filter=="No submitted trials" and participation["trials"]:continue
        if study_filter=="Has submitted trials" and not participation["trials"]:continue
        visible.append(record)
    st.caption(f"{len(visible)} / {len(records)} stimuli · newest first · study members are protected · JSON-only storage")
    signature=(choice,tuple(sorted(excluded_statuses)),study_filter,tuple(counts),page_size)
    if st.session_state.get("ambient_saved_page_filter_signature")!=signature:
        st.session_state["ambient_saved_page"]=1
        st.session_state["ambient_saved_page_filter_signature"]=signature
    page_records,page,pages=saved_page(visible,st.session_state.get("ambient_saved_page",1),page_size)
    st.session_state["ambient_saved_page"]=page
    with st.container(key="ambient_saved_pagination"):
        previous,selector,summary,next_button=st.columns([.4,1.6,4,.4],vertical_alignment="center")
        with previous:st.button("‹",key="ambient_saved_previous",help="Previous page",disabled=page==1,on_click=change_saved_page,args=(-1,pages))
        with selector:
            page=st.selectbox("Page",list(range(1,pages+1)),index=page-1,key="ambient_saved_page",label_visibility="collapsed",
                              format_func=lambda value:f"Page {value} of {pages}")
        with summary:
            start=(page-1)*page_size+1 if visible else 0
            st.caption(f"Showing {start}–{min(page*page_size,len(visible))} of {len(visible)} matching stimuli")
        with next_button:st.button("›",key="ambient_saved_next",help="Next page",disabled=page==pages,on_click=change_saved_page,args=(1,pages))
    _, epoch=playback_scope([{"stimulus_id":r["saved_id"]} for r in page_records],"Saved",())
    for name,error in errors:st.warning(f"Unreadable entry {name}: {error}")
    for error in study_errors:st.warning(error)
    if not visible:st.info("No stimuli match these filters.")
    render_library_rows(page_records,usage,bool(study_errors),epoch,cached_audio)


@lru_cache(maxsize=8)
def _registered_library_rows(js,css):
    version=hashlib.sha256((js+css).encode()).hexdigest()[:16]
    return component(f"ambient_saved_rows_{version}",html='<div class="library-root"></div>',js=js,css=css)


def render_library_rows(records,usage,unsafe_membership,epoch,cached_audio,*,key="ambient_saved_rows",read_only=False,
                        locked_ids=(),on_lock=None,preview=False,on_preview=None,allow_tag_edit=False):
    """One lightweight list, not thousands of Streamlit widgets per audition."""
    by_id={r["saved_id"]:r for r in records}
    audition_key="ambient_saved_audition" if key=="ambient_saved_rows" else f"{key}_audition"
    audio_key="ambient_library_audio" if key=="ambient_saved_rows" else f"{key}_audio"
    if preview:audio_key+="_preview5"
    request_key="ambient_library_play_request" if key=="ambient_saved_rows" else f"{key}_request"
    error_key="ambient_saved_audio_error" if key=="ambient_saved_rows" else f"{key}_error"
    rows=[]
    for record in records:
        identity=record["saved_id"];audio=record["metadata"]["rendering"]
        participation=usage.get(identity,{"studies":[],"trials":0,"tags":[]})
        inherited=" · ".join(participation["tags"]) or record.get("notes","")
        rows.append({"id":identity,"summary":f"{audio['duration_seconds']}s · {audio['timbre']} · {record['status']}",
                     "locked":identity in locked_ids,"status":record["status"],"favorite":record.get("favorite",False),"tag":record.get("tag",inherited[:64]),
                     "studies":len(participation["studies"]),"trials":participation["trials"],
                     "study_names":", ".join(item["name"] for item in participation["studies"]),
                     "protected":bool(participation["studies"] or unsafe_membership)})
    def event():
        message=st.session_state.get(key,{}).get("event")
        if not isinstance(message,dict):return
        if message.get("kind")=="preview" and on_preview and isinstance(message.get("value"),bool):
            on_preview(message["value"]);return
        if message.get("id") not in by_id:return
        identity=message["id"];record=by_id[identity]
        if message.get("kind")=="lock" and on_lock and isinstance(message.get("value"),bool):
            on_lock(identity,message["value"]);return
        try:
            kind=message.get("kind")
            if read_only and kind!="play":return
            if kind=="play":
                st.session_state[audition_key]=identity
                st.session_state[request_key]=uuid4().hex
                st.session_state.pop(error_key,None)
                loaded=st.session_state.get(audio_key)
                if not loaded or loaded[0]!=identity:
                    if preview:
                        from ambient_preview import preview_audio
                        wav=preview_audio(record["metadata"])
                    else:wav=reconstruct(record["metadata"],cached_audio)
                    loaded=(identity,wav)
                    st.session_state[audio_key]=loaded
            elif kind=="details":open_detail(record["metadata"],list(by_id).index(identity),None,identity)
            elif kind=="status" and message.get("value") in library.STATUSES:library.set_status(identity,message["value"])
            elif kind=="favorite":library.set_favorite(identity,message.get("value"))
        except (OSError,ValueError,RuntimeError,ImportError,KeyError,TypeError) as error:
            if message.get("kind")=="play":st.session_state[error_key]={"id":identity,"message":str(error)}
            st.session_state["ambient_save_notice"]=str(error)
    def tag_changed():
        if read_only and not allow_tag_edit:return
        message=st.session_state.get(key,{}).get("tag")
        if not isinstance(message,dict) or message.get("id") not in by_id:return
        try:library.set_tag(message["id"],message.get("value"))
        except (OSError,ValueError,KeyError) as error:st.session_state["ambient_save_notice"]=str(error)
    loaded=st.session_state.get(audio_key)
    active=st.session_state.get(audition_key)
    audio=None
    if loaded and loaded[0]==active and active in by_id:
        audio={"id":active,"url":audio_url(loaded[1],f"saved-{active}"),"request":st.session_state.get(request_key)}
    error=st.session_state.get(error_key)
    if error and error["id"] in by_id:st.warning(f"Cannot audition {error['id'][:8]}: {error['message']}")
    assets=Path(__file__).with_name("ambient_frontend")
    controller=(assets/"audition.js").read_text().split("export default",1)[0]
    frontend=_registered_library_rows(controller+(assets/"library.js").read_text(),(assets/"library.css").read_text())
    frontend(key=key,data={"rows":rows,"epoch":epoch,"audio":audio,"audio_error":error,"read_only":read_only,
                            "can_lock":on_lock is not None,"can_preview":on_preview is not None,"preview":preview,"can_edit_tags":allow_tag_edit},height="content",
             on_event_change=event,on_tag_change=tag_changed)


def library_actions(record):
    identity = record["saved_id"]
    usage, errors = library.study_usage()
    protected = bool(usage.get(identity) or errors)
    st.caption(f"Status: {record['status']}" + (" · study member (protected)" if protected else ""))
    st.button("Save", key=f"ambient_library_save_{identity}", disabled=record["status"] == "saved",
              on_click=status_action, args=(identity, "saved"))
    st.button("Bypass", key=f"ambient_library_bypass_{identity}", disabled=protected or record["status"] == "bypassed",
              on_click=status_action, args=(identity, "bypassed"))
    if record.get("record_type") == "collected":
        st.button("Unsave" if record["status"] == "saved" else "Unreview",
                  key=f"ambient_library_unsave_{identity}", disabled=protected or record["status"] == "unreviewed",
                  on_click=status_action, args=(identity, "unreviewed"))
    elif not protected:
        delete_control(identity)


def render_detail(cached_audio, render_details):
    detail = st.session_state["ambient_detail"]
    # These widgets aren't mounted on the detail page; retain their selections.
    for key in ("ambient_library_filter", "ambient_library_page"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    st.button("← Back", key="ambient_detail_back", on_click=close_detail)
    metadata = detail["metadata"]
    identity = detail.get("saved_id") or metadata.get("stimulus_id", "legacy")
    record = None
    if detail.get("saved_id"):
        try:
            record = library.hydrate(library.read_record(detail["saved_id"]))
        except (OSError, ValueError, KeyError):
            st.warning("The library record is unavailable; showing the opened metadata snapshot.")
    else:
        record = record_for(metadata)
    if record:
        identity = record["saved_id"]
    st.subheader("Stimulus details")
    st.code(identity, language=None)
    _, epoch = playback_scope([{"stimulus_id": identity}], "Details", (library.fingerprint(metadata),))
    try:
        if detail["wav"] is None:
            detail["wav"] = reconstruct(metadata, cached_audio)
        render_player(detail["wav"], f"detail-{identity}", epoch)
        st.download_button("Download WAV", detail["wav"], file_name=f"ambient_{identity}.wav",
                           mime="audio/wav", key="ambient_detail_wav", on_click="ignore")
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as error:
        st.warning(f"Cannot reconstruct audio: {error}")
    if record:
        st.caption(f"Collection status: {record['status']}")
        with st.popover("Status actions"):
            library_actions(record)
        key = f"ambient_notes_{record['saved_id']}"
        st.text_area("Notes · saves on blur", value=record["notes"], key=key,
                     on_change=notes_action, args=(record["saved_id"], key))
        history = " → ".join(f"{entry['status']} ({entry['at']})" for entry in record["status_history"])
        st.caption(f"History: {history or 'No historical decisions recorded'}")
        st.caption(f"Batch: {record.get('batch_id') or 'Manual/legacy — no historical batch'}")
        if record.get("batch_id"):
            with st.expander("Batch generation provenance"):
                try:
                    st.json(library.read_batch(record["batch_id"]))
                except (OSError, ValueError):
                    st.warning("Batch provenance is unavailable.")
    else:
        save_control(metadata, "detail", details=False)
    render_details(metadata, detail["index"])
