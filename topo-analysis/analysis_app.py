import streamlit as st
import textwrap
from pathlib import Path

from streamlit_plotly_events import plotly_events

from analysis_v1 import (
    scan_archive,
    apply_filters,
    build_transition_summary,
    plot_affect_trajectories,
    export_transition_summary,
    build_sample_summary,
    export_joined_rows,
    export_sample_summary,
    move_id_columns_to_end,
    make_compact_sample_table,
    build_ranked_sample_table,
    build_proximity_groups,
    assign_proximity_group_ids,
    assign_topology_group_ids,
    build_clustered_topology_plot,
    build_interactive_affect_trajectory_plot,
    build_topology_point_cloud_plot,
    build_topology_embedding,
    project_points_onto_axis,
    compute_axis_correlations,
    build_axis_correlation_curve_plot,
    build_latent_axis_point_cloud_plot,
    find_best_axis_angles,
    get_topology_fidelity,
    get_perceptual_axis_labels,
    OUTPUT_DIR
)

DEMO_MODE = str(st.secrets.get("TOPO_EXPLORER_DEMO", "false")).lower() == "true"

def set_latent_axis_angle(angle):
    st.session_state["latent_axis_angle"] = angle

toc_items = []

if "audio_play_counter" not in st.session_state:
    st.session_state["audio_play_counter"] = 0

def make_anchor(label):
    return (
        label.lower()
        .replace(" ", "-")
        .replace("/", "")
        .replace("(", "")
        .replace(")", "")
    )


def section_anchor(label, level=2):
    anchor = make_anchor(label)

    toc_items.append({
        "label": label,
        "anchor": anchor,
        "level": level
    })

    # Only create physical anchors for major sections
    if level == 2:
        st.markdown(
            f"<div id='{anchor}'></div>",
            unsafe_allow_html=True
        )

def render_sidebar_toc():
    if not toc_items:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("## Contents")

    for item in toc_items:
        indent = "&nbsp;&nbsp;" if item["level"] == 3 else ""

        st.sidebar.markdown(
            f"{indent}- [{item['label']}](#{item['anchor']})",
            unsafe_allow_html=True
        )

    st.sidebar.markdown("---")

st.set_page_config(
    page_title="Topo Explorer",
    layout="wide"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@300;400;500&display=swap');

html, body, .stApp {
    font-family: 'Roboto Mono', monospace !important;
}

.stMarkdown,
.stText,
.stMetric,
.stButton,
.stTextInput,
.stSelectbox,
.stMultiSelect,
.stSlider,
.stExpander,
.stDataFrame,
p,
label,
span:not([class*="material"]) {
    font-family: 'Roboto Mono', monospace !important;
}

/* Reduce vertical spacing inside expanders */
div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] {
    gap: 0.35rem !important;
}

/* Reduce space above markdown headings */
div[data-testid="stExpander"] h3 {
    margin-top: 0.7rem !important;
    margin-bottom: 0.25rem !important;
}

/* Reduce space around captions */
div[data-testid="stExpander"] div[data-testid="stCaptionContainer"] {
    margin-bottom: 0.2rem !important;
}

/* Reduce dataframe spacing */
div[data-testid="stExpander"] div[data-testid="stDataFrame"] {
    margin-top: 0.2rem !important;
    margin-bottom: 0.5rem !important;
}

/* Reduce button row spacing */
div[data-testid="stExpander"] div[data-testid="column"] {
    padding-top: 0.2rem !important;
    padding-bottom: 0.2rem !important;
}            


.stApp {
    background-color: #0a0a0a !important;
    color: #cfcfcf !important;
}

/* Main container */
.block-container {
    max-width: 900px !important;
    padding-top: 2rem !important;
    padding-bottom: 4rem !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #161616 !important;
    border-right: 1px solid #252525 !important;
}

section[data-testid="stSidebar"] * {
    font-size: 10px !important;
}

/* Typography */
h1 {
    font-size: 36px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    color: #e0e0e0 !important;
    margin-bottom: 30px !important;
}

h2,
h3,
div[data-testid="stHeading"] h2,
div[data-testid="stHeading"] h3,
.compact-subtitle {
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    color: #d0d0d0 !important;
    text-transform: uppercase !important;
}

p, label {
    font-size: 10px !important;
}

[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    text-transform: uppercase !important;
}

/* Buttons */
.stButton button {
    background-color: transparent !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 2px !important;
    color: #d0d0d0 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    padding: 0.45rem 0.8rem !important;
}

.stButton button:hover {
    border-color: #888888 !important;
    color: #ffffff !important;
}

/* Inputs */
.stTextInput input,
div[data-baseweb="select"] > div {
    background-color: #101010 !important;
    border: 1px solid #2a2a2a !important;
    color: #d0d0d0 !important;
    border-radius: 2px !important;
}

/* Alerts */
div[data-testid="stAlert"] {
    background-color: #111111 !important;
    border: 1px solid #2c2c2c !important;
    border-radius: 2px !important;
}

/* Expanders */
div[data-testid="stExpander"] {
    background-color: #101010 !important;
    border: 1px solid #303030 !important;
    border-radius: 2px !important;
    margin-bottom: 2px !important;
}

div[data-testid="stExpander"] details {
    background-color: #101010 !important;
}

div[data-testid="stExpander"] summary {
    background-color: #151515 !important;
    min-height: 36px !important;
    padding: 8px 12px !important;
    display: flex !important;
    align-items: center !important;
}

div[data-testid="stExpander"] summary p {
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.4 !important;
    font-size: 10px !important;
    color: #d0d0d0 !important;
}

div.element-container:has(div[data-testid="stExpander"]) + div.element-container {
    margin-top: 0px !important;
}
/* Sliders */
.stSlider [role="slider"] {
    background-color: #56acb8 !important;
    border: none !important;
    box-shadow: none !important;
    width: 10px !important;
    height: 10px !important;
}

.stSlider [data-baseweb="slider"] > div > div > div {
    height: 1px !important;
}

/* Dataframes */
div[data-testid="stDataFrame"] {
    border: 1px solid #303030 !important;
    border-radius: 2px !important;
}

div[data-testid="stDataFrame"] * {
    font-family: 'Roboto Mono', monospace !important;
    font-size: 10px !important;
}

/* Metrics */
div[data-testid="stMetric"] * {
    font-family: 'Roboto Mono', monospace !important;
    font-size: 10px !important;
}

div[data-testid="stMetricValue"] {
    font-size: 16px !important;
}
            
span[class*="material"],
span[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", sans-serif !important;
}
            

/* Top header bar */

header[data-testid="stHeader"] {
    background-color: #0a0a0a !important;
}

header[data-testid="stHeader"] * {
    color: #cfcfcf !important;
}

div[data-testid="stToolbar"] {
    background-color: transparent !important;
}            

div[data-testid="stHeading"] h1 {
    font-size: 42px !important;
    line-height: 1.15 !important;
}

/* Multiselect tags */

[data-baseweb="tag"] {
    background-color: #2a2a2a !important;
    border: 1px solid #444444 !important;
}

[data-baseweb="tag"] * {
    color: #d0d0d0 !important;
}

div[data-testid="stHeading"] h3 {
    font-size: 14px !important;
}

div[data-testid="stHeading"] h2 {
    font-size: 14px !important;
    font-weight: 500 !important;
}            


/* Slider handle */
.stSlider [role="slider"] {
    background-color: #56acb8 !important;
    border: none !important;
    box-shadow: none !important;
    width: 10px !important;
    height: 10px !important;
}

/* Glide Data Grid header */

div[data-testid="stDataFrame"] canvas {
    background-color: #151515 !important;
}

/* Sidebar TOC links */
section[data-testid="stSidebar"] a {
    color: #a8a8a8 !important;
    text-decoration: none !important;
}

section[data-testid="stSidebar"] a:hover {
    color: #d8d8d8 !important;
}
            
    /* Reduce vertical gaps between blocks */
.block-container div[data-testid="stVerticalBlock"] {
    gap: 0.75rem;
}

/* Reduce space below metrics */
[data-testid="stMetric"] {
    padding-top: 0rem;
    padding-bottom: 0rem;
}

/* Reduce column spacing */
div[data-testid="column"] {
    padding-top: 0rem;
    padding-bottom: 0rem;
}

/* Reduce margin below markdown elements */
.element-container {
    margin-bottom: 0.4rem;
}        

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

div[data-testid="stVerticalBlock"] > div {
    margin-bottom: 0.5rem;
}            
            
.compact-panel {
    margin-top: 4px;
    margin-bottom: 24px;
}

.compact-grid {
    display: grid;
    column-gap: 56px;
    row-gap: 14px;
}

.compact-grid.four {
    grid-template-columns: repeat(4, 1fr);
}

.compact-grid.three {
    grid-template-columns: repeat(3, 1fr);
}

.compact-label {
    font-size: 10px;
    color: #9a9a9a;
    margin-bottom: 5px;
    font-weight: 500;
}

.compact-value {
    font-size: 11px;
    color: #d6d6d6;
}        
            
.compact-divider {
    height: 1px;
    background: rgba(255, 255, 255, 0.10);
    margin: 10px 0;
}
            

div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stExpander"]) {
    margin-bottom: 2px !important;
    padding-bottom: 0px !important;
}

div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stExpander"]) + div:has(div[data-testid="stExpander"]) {
    margin-top: 0px !important;
}            

div[data-testid="stVerticalBlock"] > div {
    gap: 0rem !important;
}            

</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <div style="
        font-family: 'Roboto Mono', monospace;
        font-size: 24px;
        font-weight: 500;
        color: #e0e0e0;
        letter-spacing: 0.02em;
        line-height: 1.4;
        padding-top: 10px;
        padding-bottom: 20px;
    ">
        Topology Explorer
    </div>
    """,
    unsafe_allow_html=True
)

rows = scan_archive()


available_methodologies = sorted(
    set(row["methodology_id"] for row in rows)
)
if DEMO_MODE:
    available_methodologies = [
        methodology
        for methodology in available_methodologies
        if methodology == "vector_v2"
    ]

available_sample_sets = sorted(
    set(row["sample_set_id"] for row in rows)
)

available_temporal_scales = sorted(
    set(
        row.get("temporal_integration_scale", "Unknown")
        for row in rows
    )
)

st.sidebar.header("Analysis Scope")


if DEMO_MODE:
    participant_number = st.sidebar.text_input(
        "Participant Number",
        value="",
        disabled=True
    )
    participant_filter = None
    st.sidebar.caption("Disabled in demo mode")
else:
    participant_number = st.sidebar.text_input(
        "Participant Number",
        value=""
    )

    participant_filter = None

    if participant_number.strip():
        try:
            participant_filter = f"P{int(participant_number):03d}"
        except ValueError:
            st.sidebar.error("Participant number must be numeric.")
            participant_filter = "__INVALID__"

st.sidebar.caption(
    f"Participant ID: {participant_filter or 'ALL'}"
)

if not available_methodologies:
    st.warning("No methodologies found in the archive.")
    st.stop()

preferred_methodology = (
    "vector_v2"
    if "vector_v2" in available_methodologies
    else available_methodologies[0]
)

if DEMO_MODE:
    methodology_filter = "vector_v2"
    st.sidebar.caption("Methodology: vector_v2")
else:
    methodology_choice = st.sidebar.selectbox(
        "Methodology",
        options=available_methodologies,
        index=available_methodologies.index(preferred_methodology),
        help=(
            "Choose exactly one mapping methodology. Mixed-method topology "
            "combination is intentionally disabled for now."
        )
    )

    methodology_filter = methodology_choice


if DEMO_MODE:
    temporal_scale_choice = (
        "Local Scale"
        if "Local Scale" in available_temporal_scales
        else available_temporal_scales[0]
    )
    st.sidebar.selectbox(
        "Temporal Scale",
        options=[temporal_scale_choice],
        index=0,
        disabled=True
    )
    st.sidebar.caption("Disabled in demo mode")
else:
    temporal_scale_choice = st.sidebar.selectbox(
        "Temporal Scale",
        options=available_temporal_scales,
        index=(
            available_temporal_scales.index("Local Scale")
            if "Local Scale" in available_temporal_scales
            else 0
        )
    )

if DEMO_MODE:
    sample_set_filter = None
    st.sidebar.multiselect(
        "Sample Sets",
        options=["ALL"],
        default=["ALL"],
        disabled=True
    )
    st.sidebar.caption("Disabled in demo mode")
else:
    sample_set_choices = st.sidebar.multiselect(
        "Sample Sets",
        options=["ALL"] + available_sample_sets,
        default=["ALL"]
    )

available_trial_sets = sorted(
    set(row["trial_id"] for row in rows)
)

trial_set_choices = st.sidebar.multiselect(
    "Trial Sets",
    options=["ALL"] + available_trial_sets,
    default=["ALL"]
)

if "ALL" in trial_set_choices and len(trial_set_choices) > 1:
    trial_set_choices = [
        choice for choice in trial_set_choices
        if choice != "ALL"
    ]

if "ALL" in trial_set_choices:
    trial_set_filter = None
else:
    trial_set_filter = trial_set_choices

if DEMO_MODE:
    sample_set_filter = None
else:
    if "ALL" in sample_set_choices and len(sample_set_choices) > 1:
        sample_set_choices = [
            choice for choice in sample_set_choices
            if choice != "ALL"
        ]

    if "ALL" in sample_set_choices:
        sample_set_filter = None
    else:
        sample_set_filter = sample_set_choices

if DEMO_MODE and "demo_initialized" not in st.session_state:
    run_analysis = True
    st.session_state["demo_initialized"] = True
else:
    run_analysis = st.sidebar.button("Run Analysis")

if run_analysis:

    filters = {
        "participant_id": participant_filter or None,
        "methodology_id": methodology_filter or None,
        "sample_set_id": sample_set_filter or None,
        "trial_set_id": trial_set_filter or None,
        "temporal_integration_scale": temporal_scale_choice,
    }

    filtered_rows = apply_filters(rows, filters)

    st.session_state["rows"] = rows
    st.session_state["filtered_rows"] = filtered_rows
    st.session_state["filters"] = filters
    st.session_state["analysis_complete"] = True


    
if st.session_state.get("analysis_complete"):
    st.sidebar.success("Analysis complete")













if "filtered_rows" in st.session_state:

    rows = st.session_state["rows"]
    filtered_rows = st.session_state["filtered_rows"]
    if not filtered_rows:
        st.warning("No rows match the current filters.")
        st.stop()    
    filters = st.session_state["filters"]



    # EVERYTHING ELSE GOES HERE

    participants = len(
        set(r["participant_id"] for r in filtered_rows)
    )

    methodologies = len(
        set(r["methodology_id"] for r in filtered_rows)
    )

    sample_sets = len(
        set(r["sample_set_id"] for r in filtered_rows)
    )

    section_anchor("Dataset Summary", level=2)
    st.subheader(
        "DATASET SUMMARY",
        help=(
            "Overview of the currently filtered dataset, including the number "
            "of participants, methodologies, sample sets, and observations "
            "included in this analysis."
        )
    )

    sample_set_text = (
        "ALL"
        if sample_set_filter is None
        else ", ".join(sample_set_filter)
    )

    summary_html = textwrap.dedent(f"""
    <div class="compact-panel">

        <div class="compact-grid four">
            <div>
                <div class="compact-label">Participants</div>
                <div class="compact-value">{participants}</div>
            </div>

            <div>
                <div class="compact-label">Methodologies</div>
                <div class="compact-value">{methodologies}</div>
            </div>

            <div>
                <div class="compact-label">Sample Sets</div>
                <div class="compact-value">{sample_sets}</div>
            </div>

            <div>
                <div class="compact-label">Observations</div>
                <div class="compact-value">{len(filtered_rows)}</div>
            </div>
        </div>

        <div class="compact-divider"></div>

        <div class="compact-subtitle">ACTIVE FILTERS</div>

        <div class="compact-grid three">
            <div>
                <div class="compact-label">Participant</div>
                <div class="compact-value">{participant_filter or "ALL"}</div>
            </div>

            <div>
                <div class="compact-label">Methodology</div>
                <div class="compact-value">{methodology_filter or "ALL"}</div>
            </div>

            <div>
                <div class="compact-label">Sample Sets</div>
                <div class="compact-value">{sample_set_text}</div>
            </div>
        </div>

    </div>
    """)
    st.html(summary_html)

    section_anchor("Sample-Level Findings", level=2)
    st.markdown(
        "## SAMPLE-LEVEL FINDINGS",
        help=(
            "Exploratory analyses that identify notable patterns among individual "
            "samples, such as perceptual clusters, large movements, and strong "
            "changes in brightness or stability."
        )
    )


    section_anchor("Perceptual Rankings", level=3)

    with st.expander("Perceptual Rankings", expanded=False):

        st.caption(
            """
            Rank samples by a selected perceptual measurement. This replaces
            the separate longest movement, brightness increase/decrease, and
            stability increase/loss sections.
            """
        )

        axis_labels = get_perceptual_axis_labels(filtered_rows[0])

        metric_options = {
            "Movement Length": "length_norm",
            axis_labels["y_label"]: "delta_brightness",
            axis_labels["x_label"]: "delta_stability",
            "Movement DX": "movement_dx",
            "Movement DY": "movement_dy"
        }

        col1, col2, col3 = st.columns(3)

        metric_label = col1.selectbox(
            "Metric",
            options=list(metric_options.keys())
        )

        ranking_mode = col2.selectbox(
            "Ranking Mode",
            options=[
                "Highest Values",
                "Lowest Values",
                "Absolute Magnitude"
            ]
        )

        limit = col3.number_input(
            "Number of Samples",
            min_value=1,
            max_value=len(filtered_rows),
            value=min(10, len(filtered_rows)),
            step=1
        )

        ranked_rows = build_ranked_sample_table(
            filtered_rows,
            metric_options[metric_label],
            ranking_mode,
            limit
        )

        st.dataframe(
            ranked_rows,
            use_container_width=True
        )

    section_anchor("Movement Vectors", level=3)
    with st.expander("Movement Vectors", expanded=False):

        vector_rows = []

        for row in filtered_rows:

            vector_rows.append({
                "sample_id": row["sample_id"],
                "degree_transition": row["degree_transition"],
                "movement_dx": round(
                    row["movement_dx"],
                    3
                ),
                "movement_dy": round(
                    row["movement_dy"],
                    3
                )
            })

        st.dataframe(
            move_id_columns_to_end(vector_rows),
            use_container_width=True
        )

    section_anchor("Inspection", level=2)
    st.markdown("## INSPECTION")


    section_anchor("Topology Point Cloud", level=3)
    with st.expander(
        "Topology Point Cloud",
        expanded=True
    ):

        st.caption(
            """
            Choose the unit of analysis before constructing the topology.
            Observation Mode keeps every mapping separate. Participant-Sample
            Mode collapses repeats by participant and sample. Sample Aggregate
            Mode collapses all matching sample IDs into one topology point.
            """
        )

        if DEMO_MODE:
            topology_unit = "Sample Aggregate"
            st.caption("Topology Unit: Sample Aggregate")
        else:
            topology_unit = st.radio(
                "Topology Unit",
                options=[
                    "Sample Aggregate",
                    "Participant-Sample",
                    "Observation"
                ],
                horizontal=True,
                help=(
                    "Controls whether repeated samples are collapsed before MDS. "
                    "Sample Aggregate is best for a collective sample topology; "
                    "Observation is best for raw response clouds."
                )
            )

        n_components = 2

        topology_rows, stress = build_topology_embedding(
            filtered_rows,
            n_components=n_components,
            topology_unit=topology_unit
        )

        if len(topology_rows) < 2:
            st.warning(
                "Not enough topology units to build an embedding. "
                "Try a broader filter or use Observation Mode."
            )
            st.stop()

        fidelity = get_topology_fidelity(
            stress
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Embedding Dimensions",
            str(n_components),
            help=(
                "The number of dimensions used to render the topology. "
                "This is currently 2D, meaning the perceptual distance structure "
                "is compressed into a flat point cloud."
            )
        )

        col2.metric(
            "MDS Stress",
            f"{stress:.3f}",
            help=(
                "Measures how faithfully the visible topology preserves the "
                "original perceptual distances between samples. Lower values "
                "indicate a more trustworthy embedding.\n\n"
                "Approximate guide:\n"
                "0.00 = perfect preservation\n"
                "< 0.05 = excellent\n"
                "0.05–0.10 = good\n"
                "0.10–0.20 = moderate distortion\n"
                "> 0.20 = poor representation"
            )
        )

        col3.metric(
            "Topology Fidelity",
            fidelity,
            help=(
                "A rough interpretation of the MDS stress value. Higher fidelity "
                "means the visible point cloud can be trusted more as a map of "
                "perceptual similarity."
            )
        )

        col4.metric(
            "Topology Points",
            str(len(topology_rows)),
            help=(
                "The number of units actually embedded after applying the "
                "selected topology-unit collapse mode."
            )
        )

        best_angle_rows = find_best_axis_angles(
            topology_rows
        )



        topology_mode = st.radio(
            "Topology Mode",
            options=[
                "Latent Axis Explorer",
                "Clustering Explorer",
            ],
            index=1 if DEMO_MODE else 0,
            horizontal=True,
            help=(
                "Switch between interpretive-axis analysis and proximity-based "
                "group visualization. Both modes use the same topology point cloud."
            ),
        )

        if topology_mode == "Latent Axis Explorer":

            if "latent_axis_angle" not in st.session_state:
                st.session_state["latent_axis_angle"] = 0

            angle = st.session_state["latent_axis_angle"]

            axis_fig = build_latent_axis_point_cloud_plot(
                topology_rows,
                angle
            )

            clicked_points = plotly_events(
                axis_fig,
                click_event=True,
                hover_event=False,
                select_event=False,
                override_height=500,
                key=f"latent_axis_plot_{angle}",
            )

            st.caption("Click any point in the topology to hear its audio sample.")

            if clicked_points:
                clicked_index = clicked_points[0]["pointIndex"]

                if 0 <= clicked_index < len(topology_rows):
                    selected_topology_row = topology_rows[clicked_index]

                    st.session_state["selected_topology_sample_id"] = (
                        selected_topology_row["sample_id"]
                    )
                    st.session_state["selected_topology_label"] = (
                        selected_topology_row.get(
                            "topology_label",
                            selected_topology_row["sample_id"]
                        )
                    )
                

            angle = st.slider(
                "Axis Angle (degrees)",
                min_value=0,
                max_value=180,
                key="latent_axis_angle",
                help=(
                    "Rotates the interpretive axis through the topology. "
                    "The topology itself does not change; only the analysis "
                    "direction changes."
                )
            )

            projected_rows = project_points_onto_axis(
                topology_rows,
                angle
            )

            correlation_rows = compute_axis_correlations(
                topology_rows,
                angle
            )

            # keep the rest of your current axis correlation,
            # snap buttons, best axis angles, curve plot,
            # and projected positions code indented here

            st.markdown("### Axis Correlations")
            st.caption(
                "How strongly the current axis aligns with each variable.",
                help=(
                    "Correlation compares each sample's position along the "
                    "current axis with its measured variables. Higher absolute "
                    "values mean stronger alignment."
                )
            )

            st.dataframe(
                correlation_rows,
                use_container_width=True
            )

            st.markdown("### Snap to Best Axis")

            best_angle_lookup = {
                row["variable"]: row["best_angle"]
                for row in best_angle_rows
            }

            axis_labels = get_perceptual_axis_labels(topology_rows[0])

            y_variable = axis_labels["y_label"]
            x_variable = axis_labels["x_label"]
            length_variable = "Length"

            col1, col2, col3 = st.columns(3)

            col1.button(
                f"{y_variable}",
                help=(
                    f"Jump to the axis angle with the strongest absolute "
                    f"correlation to {y_variable.lower()}."
                ),
                on_click=set_latent_axis_angle,
                args=(
                    best_angle_lookup[y_variable],
                )
            )

            col2.button(
                f"{x_variable}",
                help=(
                    f"Jump to the axis angle with the strongest absolute "
                    f"correlation to {x_variable.lower()}."
                ),
                on_click=set_latent_axis_angle,
                args=(
                    best_angle_lookup[x_variable],
                )
            )

            col3.button(
                "Length",
                help=(
                    "Jump to the axis angle with the strongest absolute "
                    "correlation to perceived movement length."
                ),
                on_click=set_latent_axis_angle,
                args=(
                    best_angle_lookup[length_variable],
                )
            )

            st.markdown("### Best Axis Angles")
            st.caption(
                "The strongest angle found for each variable.",
                help=(
                    "These angles maximize absolute correlation. A positive or "
                    "negative sign only indicates direction along the axis."
                )
            )

            st.dataframe(
                best_angle_rows,
                use_container_width=True
            )

            st.markdown("### Correlation by Axis Angle")
            st.caption(
                "Shows how strongly each variable aligns at every axis angle.",
                help=(
                    "Peaks indicate directions through the topology that may "
                    "correspond to latent perceptual dimensions."
                )
            )

            curve_fig = build_axis_correlation_curve_plot(
                topology_rows
            )

            st.plotly_chart(
                curve_fig,
                use_container_width=True
            )

            preview_rows = []

            for row in projected_rows:
                preview_rows.append({
                    "sample_id": row["sample_id"],
                    "axis_position": round(
                        row["axis_position"],
                        3
                    )
                })

        elif topology_mode == "Clustering Explorer":

            if "cluster_max_distance" not in st.session_state:
                st.session_state["cluster_max_distance"] = 0.15

            if "cluster_grouping_mode" not in st.session_state:
                st.session_state["cluster_grouping_mode"] = "Topology Proximity"

            max_distance = st.session_state["cluster_max_distance"]
            grouping_mode = st.session_state["cluster_grouping_mode"]

            if grouping_mode == "Topology Proximity":
                grouped_topology_rows = assign_topology_group_ids(
                    topology_rows,
                    max_distance
                )

            else:
                grouped_topology_rows = assign_proximity_group_ids(
                    topology_rows,
                    max_distance
                )

            cluster_fig = build_clustered_topology_plot(
                grouped_topology_rows
            )

            st.caption("Click any point in the topology to hear its audio sample.")

            clicked_cluster_points = plotly_events(
                cluster_fig,
                click_event=True,
                hover_event=False,
                select_event=False,
                override_height=500,
                key=f"cluster_plot_{max_distance}_{grouping_mode}_{topology_unit}"
            )

            if clicked_cluster_points:
                clicked_curve = clicked_cluster_points[0]["curveNumber"]
                clicked_point = clicked_cluster_points[0]["pointIndex"]

                group_ids = sorted(
                    set(row["group_id"] for row in grouped_topology_rows)
                )

                if 0 <= clicked_curve < len(group_ids):
                    clicked_group_id = group_ids[clicked_curve]

                    clicked_group_rows = [
                        row for row in grouped_topology_rows
                        if row["group_id"] == clicked_group_id
                    ]

                    if 0 <= clicked_point < len(clicked_group_rows):
                        selected_topology_row = clicked_group_rows[clicked_point]

                        st.session_state["selected_topology_sample_id"] = (
                            selected_topology_row["sample_id"]
                        )
                        st.session_state["selected_topology_label"] = (
                            selected_topology_row.get(
                                "topology_label",
                                selected_topology_row["sample_id"]
                            )
                        )
                                  

            max_distance = st.slider(
                "Maximum perceptual distance",
                min_value=0.00,
                max_value=1.00,
                step=0.01,
                key="cluster_max_distance",
                help=(
                    "Controls how close samples must be to be assigned "
                    "to the same group."
                )
            )

            grouping_mode = st.radio(
                "Grouping Distance",
                options=[
                    "Topology Proximity",
                    "Trajectory Similarity"
                ],
                horizontal=True,
                key="cluster_grouping_mode",
                help=(
                    "Topology Proximity groups by distances in the rendered "
                    "point cloud. Trajectory Similarity groups by the original "
                    "affect trajectory distances."
                )
            )

            group_options = sorted(
                set(row["group_id"] for row in grouped_topology_rows)
            )

            selected_group = st.selectbox(
                "Inspect Group",
                options=group_options,
                help=(
                    "Choose one group to inspect. This avoids displaying "
                    "large tables for every group at once."
                )
            )

            selected_group_rows = [
                row for row in grouped_topology_rows
                if row["group_id"] == selected_group
            ]

            st.dataframe(
                make_compact_sample_table(
                    selected_group_rows
                ),
                use_container_width=True
            )       

        if "selected_topology_sample_id" in st.session_state:
            selected_sample_id = st.session_state["selected_topology_sample_id"]

            matching_rows = [
                row for row in filtered_rows
                if row["sample_id"] == selected_sample_id
            ]

            if matching_rows:
                selected_row = matching_rows[0]

                selected_label = st.session_state.get(
                    "selected_topology_label",
                    selected_sample_id
                )

                st.write(f"Selected topology unit: {selected_label}")

                audio_path = selected_row.get("audio_path")

                if audio_path is None:
                    st.warning("No audio_path found. Run Analysis again.")
                elif Path(audio_path).exists():
                    st.audio(audio_path, autoplay=True)
                else:
                    st.warning(f"Audio file not found:\n{audio_path}")                     



    with st.expander("Affect Trajectories", expanded=True):
        fig = build_interactive_affect_trajectory_plot(
            filtered_rows
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with st.expander("Sample Inspector", expanded=True):

        selected_sample = st.selectbox(
            "Inspect Sample",
            options=[
                row["sample_id"]
                for row in filtered_rows
            ]
        )

        selected_rows = [
            row for row in filtered_rows
            if row["sample_id"] == selected_sample
        ]

        if selected_rows:
            selected_row = selected_rows[0]

            st.markdown("### Sample Overview")

            st.write(f"Sample ID: {selected_row['sample_id']}")
            st.write(f"Transition: {selected_row['degree_transition']}")
            st.write(f"Length: {selected_row['length_norm']:.3f}")
            st.write(
                f"{selected_row.get('perceptual_x_label', 'Δ Stability')}: "
                f"{selected_row.get('perceptual_x_value', selected_row['delta_stability']):.3f}"
            )

            st.write(
                f"{selected_row.get('perceptual_y_label', 'Δ Brightness')}: "
                f"{selected_row.get('perceptual_y_value', selected_row['delta_brightness']):.3f}"
            )

            st.markdown("### Harmonic Details")

            st.write(f"Chord Type: {selected_row['event_1_chord_type']} → {selected_row['event_2_chord_type']}")
            st.write(f"Inversion: {selected_row['event_1_inversion']} → {selected_row['event_2_inversion']}")
            st.write(f"Notes 1: {selected_row['event_1_notes_names']}")
            st.write(f"Notes 2: {selected_row['event_2_notes_names']}")



    with st.expander("Sample Summary", expanded=False):

        sample_rows = build_sample_summary(
            filtered_rows
        )

        st.dataframe(
            move_id_columns_to_end(sample_rows),
            use_container_width=True
        )


    if not DEMO_MODE:
        section_anchor("Export", level=2)
        st.markdown("## EXPORT")

        with st.expander("Export Results", expanded=False):
            export_joined = st.checkbox("Joined dataset", value=True)
            export_transition = st.checkbox("Transition summary", value=True)
            export_sample = st.checkbox("Sample summary", value=True)

            if st.button("Export Selected CSVs"):

                if export_joined:
                    export_joined_rows(filtered_rows)

                if export_transition:
                    export_transition_summary(filtered_rows)

                if export_sample:
                    export_sample_summary(filtered_rows)

                st.success("Selected CSV results exported to output folder.")

        render_sidebar_toc()