"""On-demand 5-second previews and 30-second listening; no persistent writes."""
from uuid import uuid4
import streamlit as st

from ambient_audio import render_states_wav
from ambient_soundfont import render_soundfont_wav
from ambient_playback import render_player

PREVIEW_SECONDS = 5


@st.cache_data(max_entries=2, show_spinner=False)
def cached_preview_audio(states, duration, timbre, reverb, renderer_version,
                         soundfont=None, program=None, reverb_mode="Dry", effect_level=0.0):
    # Separate small cache: previews cannot evict the current batch's full audio.
    if duration not in (PREVIEW_SECONDS,15,30): raise ValueError("Alternate playback uses a 5-, 15-, or 30-second musical duration.")
    if soundfont is not None:
        return render_soundfont_wav(states,duration,soundfont,program,reverb_mode,effect_level)
    return render_states_wav(states,duration,timbre,reverb)


def preview_audio(metadata, duration=PREVIEW_SECONDS):
    from ambient_saved import reconstruct
    def resized(states, original_duration, *settings):
        return cached_preview_audio(states,duration,*settings)
    # Validate the original recipe, timing, renderer version and SF2 identity;
    # override duration only at the renderer call, never in the source metadata.
    return reconstruct(metadata,resized)


def request_preview(metadata, fingerprint):
    try:
        wav=preview_audio(metadata)
        st.session_state["ambient_fast_preview"]={"fingerprint":fingerprint,"wav":wav,"seconds":PREVIEW_SECONDS,"request":uuid4().hex}
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError) as error:
        st.session_state["ambient_save_notice"]=f"Fast preview unavailable: {error}"


def render_preview_control(metadata, index, fingerprint, epoch):
    active=st.session_state.get("ambient_fast_preview",{})
    if active.get("fingerprint")==fingerprint and active.get("seconds")==PREVIEW_SECONDS:
        render_player(active["wav"],f"fast-preview-{metadata.get('stimulus_id') or fingerprint}",epoch,
                      compact=True,play_request=active["request"],preview_seconds=PREVIEW_SECONDS)
    else:
        st.button("▶",key=f"ambient_fast_preview_load_{index}",type="tertiary",help="Fast preview · 5 seconds · click to restart",
                  on_click=request_preview,args=(metadata,fingerprint))
