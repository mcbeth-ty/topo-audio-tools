import json
import csv
import matplotlib.pyplot as plt
from pathlib import Path
import plotly.graph_objects as go
from sklearn.manifold import MDS
import math
import numpy as np
from scipy.stats import pearsonr
import plotly.io as pio

PLOT_FONT = "Arial, Helvetica, sans-serif"

pio.templates.default = "plotly_dark"

BASE_DIR = Path(__file__).parent

import streamlit as st

DEMO_MODE = str(st.secrets.get("TOPO_EXPLORER_DEMO", "false")).lower() == "true"

ARCHIVE_DIR = BASE_DIR / "archive"
DEMO_ARCHIVE_DIR = BASE_DIR / "demo_archive"

SAMPLE_SETS_DIR = ARCHIVE_DIR / "sample_sets"
AUDIO_DIR = (
    DEMO_ARCHIVE_DIR / "audio"
    if DEMO_MODE
    else ARCHIVE_DIR / "audio"
)

PARTICIPANT_TRIALS_DIR = (
    DEMO_ARCHIVE_DIR / "participant_trials"
    if DEMO_MODE
    else ARCHIVE_DIR / "participant_trials"
)

OUTPUT_DIR = BASE_DIR / "output"

OUTPUT_PATH = OUTPUT_DIR / "joined_harmonic_mapping_data.csv"
TRANSITION_SUMMARY_PATH = OUTPUT_DIR / "transition_summary.csv"
SAMPLE_SUMMARY_PATH = OUTPUT_DIR / "sample_summary.csv"

VERBOSE = True

FILTERS = {
    "participant_id": None,
    "methodology_id": None,
    "sample_set_id": "260530_17_37_Dm_2HE",
}

#none means include everything 

def auto_zoom_topology_axes(fig, topology_rows, padding_ratio=0.22, min_half_range=0.12):
    x_values = [row["topo_x"] for row in topology_rows]
    y_values = [row["topo_y"] for row in topology_rows]

    if not x_values or not y_values:
        return fig

    xmin = min(x_values)
    xmax = max(x_values)
    ymin = min(y_values)
    ymax = max(y_values)

    x_center = (xmin + xmax) / 2
    y_center = (ymin + ymax) / 2

    x_span = xmax - xmin
    y_span = ymax - ymin

    x_half = max((x_span / 2) * (1 + padding_ratio), min_half_range)
    y_half = max((y_span / 2) * (1 + padding_ratio), min_half_range)

    fig.update_xaxes(range=[x_center - x_half, x_center + x_half])
    fig.update_yaxes(range=[y_center - y_half, y_center + y_half])

    return fig


def get_perceptual_axis_labels(row):
    if row.get("methodology_id") == "vector_v2":
        return {
            "x_metric": "delta_arrival",
            "y_metric": "delta_valence",
            "x_label": "Δ Arrival",
            "y_label": "Δ Valence",
            "x_title": "Arrival / Departure",
            "y_title": "Valence",
        }

    return {
        "x_metric": "delta_stability",
        "y_metric": "delta_brightness",
        "x_label": "Δ Stability",
        "y_label": "Δ Brightness",
        "x_title": "Stability",
        "y_title": "Brightness",
    }


def semitone_to_interval_label(semitones):
    interval_map = {
        0: "P1",
        1: "m2",
        2: "M2",
        3: "m3",
        4: "M3",
        5: "P4",
        6: "TT",
        7: "P5",
        8: "m6",
        9: "M6",
        10: "m7",
        11: "M7",
    }

    direction = "+" if semitones >= 0 else "-"
    interval_class = abs(semitones) % 12

    return f"{direction}{interval_map.get(interval_class, str(interval_class))}"


def get_harmonic_object_quality(event):
    notes = event.get("notes_midi", [])
    root = event.get("root_note_midi")

    if root is None or not notes:
        return event.get("chord_type", "unknown")

    intervals = sorted({
        (note - root) % 12
        for note in notes
    })

    if intervals == [0, 4, 7]:
        return "M"

    if intervals == [0, 3, 7]:
        return "m"

    if intervals == [0, 3, 6]:
        return "dim"

    if intervals == [0, 4, 8]:
        return "aug"

    if intervals == [0, 4]:
        return "M3 dyad"

    if intervals == [0, 3]:
        return "m3 dyad"

    if intervals == [0, 7]:
        return "P5 dyad"

    if len(intervals) == 2:
        return "dyad"

    if len(intervals) == 3:
        return "triad"

    return "unknown"


def build_chord_relationship_label(e1, e2):
    root_1 = e1.get("root_note_midi", e1.get("root_semitone"))
    root_2 = e2.get("root_note_midi", e2.get("root_semitone"))

    if root_1 is None or root_2 is None:
        return "unknown"

    root_motion = root_2 - root_1

    quality_1 = get_harmonic_object_quality(e1)
    quality_2 = get_harmonic_object_quality(e2)

    interval_label = semitone_to_interval_label(root_motion)

    return f"{quality_1} {interval_label} {quality_2}"


def apply_topology_plot_theme(fig):

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#0a0a0a",
        paper_bgcolor="#0a0a0a",

        margin=dict(
            l=60,
            r=20,
            t=40,
            b=60
        ),

        hoverlabel=dict(
            bgcolor="#151515",
            font_color="#d0d0d0",
            bordercolor="#444444"
        ),

        font=dict(
            family=PLOT_FONT,
            size=8,
            color="#d0d0d0"
        ),

        xaxis_title_font=dict(
            family=PLOT_FONT,
            size=10,
            color="#d0d0d0"
        ),

        yaxis_title_font=dict(
            family=PLOT_FONT,
            size=10,
            color="#d0d0d0"
        )
    )

    fig.update_xaxes(
        gridcolor="#2b2f3a",
        linecolor="#2b2f3a",
        tickfont=dict(
            family=PLOT_FONT,
            size=8,
            color="#d0d0d0"
        ),
        title_font=dict(
            family=PLOT_FONT,
            size=10,
            color="#d0d0d0"
        )
    )

    fig.update_yaxes(
        gridcolor="#2b2f3a",
        linecolor="#2b2f3a",
        tickfont=dict(
            family=PLOT_FONT,
            size=8,
            color="#d0d0d0"
        ),
        title_font=dict(
            family=PLOT_FONT,
            size=10,
            color="#d0d0d0"
        )
    )

    return fig

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_event(sample, index):
    return sample["events"][index]

def plot_affect_trajectories(rows, output_dir):

    fig, ax = plt.subplots(figsize=(10, 8))

    for r in rows:

        x1 = r["start_stability"]
        y1 = r["start_brightness"]

        x2 = r["end_stability"]
        y2 = r["end_brightness"]

        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="->",
                linewidth=1.5
            )
        )

        # start point only
        ax.scatter(x1, y1, s=40)

        sample_num = r["sample_id"].split("_")[-1]

        ax.text(
            x1 + 0.005,
            y1 + 0.005,
            sample_num
        )

    ax.set_xlabel("Stability")
    ax.set_ylabel("Brightness")
    ax.set_title("Affect Trajectories")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    ax.grid(True)

    output_path = output_dir / "affect_trajectories.png"

    fig.savefig(output_path, dpi=300, bbox_inches="tight")

    print(f"Saved trajectory plot: {output_path}")
    return fig

def build_interactive_affect_trajectory_plot(rows):
    fig = go.Figure()

    for row in rows:

        axis_labels = get_perceptual_axis_labels(row)
        hover_text = (
            f"{row['sample_id']}<br>"
            f"Transition: {row['degree_transition']}<br>"
            f"Notes: "
            f"{row['event_1_notes_names']} → "
            f"{row['event_2_notes_names']}<br>"
            f"{axis_labels['x_label']}: "
            f"{row['delta_stability']:.3f}<br>"
            f"{axis_labels['y_label']}: "
            f"{row['delta_brightness']:.3f}"
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    row["plot_start_x"],
                    row["plot_end_x"]
                ],
                y=[
                    1 - row["plot_start_y"],
                    1 - row["plot_end_y"]
                ],
                mode="lines",
                line=dict(
                    width=1,
                    color="rgba(160,160,160,0.6)"
                ),                
                name=row["sample_id"],
                hovertemplate=(
                    f"{hover_text}"
                    "<extra></extra>"
                ),
                
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[row["plot_start_x"]],
                y=[1 - row["plot_start_y"]],
                mode="markers",
                marker=dict(
                    symbol="circle-open",
                    size=8,
                    color="rgba(160,160,160,0.9)"
                ),
                name=row["sample_id"],
                hovertemplate=(
                    f"{hover_text}"
                    "<extra></extra>"
                ),
                showlegend=False
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[row["plot_end_x"]],
                y=[1 - row["plot_end_y"]],
                mode="markers",
                marker=dict(
                    symbol="circle",
                    size=8,
                    color="rgba(160,160,160,0.9)"
                ),
                name=row["sample_id"],
                hovertemplate=(
                    f"{hover_text}"
                    "<extra></extra>"
                ),
                showlegend=False
            )
        )

    fig.update_layout(
        title="Affect Trajectories",
        xaxis_title=get_perceptual_axis_labels(rows[0])["x_title"],
        yaxis_title=get_perceptual_axis_labels(rows[0])["y_title"],
        xaxis=dict(range=[0, 1]),
        yaxis=dict(range=[0, 1]),
        showlegend=False,
        height=700
    )

    return fig

def get_sample_set_id(sample_id):
    parts = sample_id.split("_")
    return "_".join(parts[:-1])

def find_sampleset_file(sample_set_id):
    return SAMPLE_SETS_DIR / f"{sample_set_id}_sampleset.json"

def find_audio_file(sample_id):
    sample_set_id = get_sample_set_id(sample_id)

    candidates = [
        AUDIO_DIR / sample_set_id / f"{sample_id}.wav",
        AUDIO_DIR / f"{sample_id}.wav",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches = list(AUDIO_DIR.glob(f"**/{sample_id}.wav"))

    if matches:
        return matches[0]

    return AUDIO_DIR / sample_set_id / f"{sample_id}.wav"

def scan_archive():
    sample_set_files = list(SAMPLE_SETS_DIR.glob("*_sampleset.json"))
    mapping_files = list(PARTICIPANT_TRIALS_DIR.glob("**/*.json"))

    rows = []

    print("\n=== Archive Scan ===")
    print(f"Found sample sets: {len(sample_set_files)}")
    print(f"Found mapping trials: {len(mapping_files)}")

    if VERBOSE:
        print("\nSample set files:")
        for path in sample_set_files:
            print(f"- {path.name}")

        print("\nMapping trials:")

    for path in mapping_files:
        mapping = load_json(path)
        trial_meta = mapping["trial_metadata"]

        participant_id = trial_meta.get("participant_id", "UNKNOWN")
        methodology_id = trial_meta.get("methodology_id", "UNKNOWN")
        trial_id = trial_meta.get("trial_id", "UNKNOWN")

        sample_set_ids = sorted({
            get_sample_set_id(obs["sample_id"])
            for obs in mapping["mapping_observations"]
        })

        sample_sets_text = ", ".join(sample_set_ids)

        if VERBOSE:
            print(
                f"- {participant_id} | "
                f"{methodology_id} | "
                f"{trial_id} | "
                f"sample sets: {sample_sets_text}"
            )

        for sample_set_id in sample_set_ids:
            sampleset_path = find_sampleset_file(sample_set_id)

            if VERBOSE:
                print(f"    -> {sampleset_path.name}")

            if not sampleset_path.exists():
                if VERBOSE:
                    print("       MISSING!")
                continue

            sampleset = load_json(sampleset_path)

            global_settings = sampleset.get(
                "global_settings",
                {}
            )

            temporal_integration_scale = global_settings.get(
                "temporal_integration_scale",
                "Unknown"
            )

            duration_seconds = global_settings.get(
                "duration_seconds",
                None
            )

            temporal_integration_window_seconds = global_settings.get(
                "temporal_integration_window_seconds",
                None
            )

            temporal_integration_scale_description = global_settings.get(
                "temporal_integration_scale_description",
                None
            )            

            sample_count = len(sampleset["samples"])

            if VERBOSE:
                print(f"       samples: {sample_count}")

            sample_lookup = {
                sample["sample_id"]: sample
                for sample in sampleset["samples"]
            }

            matched_count = 0
            missing_count = 0
            printed_example = False

            for obs in mapping["mapping_observations"]:
                sample_id = obs["sample_id"]

                if sample_id in sample_lookup:
                    matched_count += 1

                    sample = sample_lookup[sample_id]

                    e1 = sample["events"][0]
                    e2 = sample["events"][1]

            

                    e1_numeric_degree = e1.get(
                        "scale_degree",
                        e1.get("root_semitone", e1.get("root_degree", "UNKNOWN"))
                    )

                    e2_numeric_degree = e2.get(
                        "scale_degree",
                        e2.get("root_semitone", e2.get("root_degree", "UNKNOWN"))
                    )

                    e1_label = e1.get(
                        "display_label",
                        e1.get("roman_numeral", e1.get("root_degree", str(e1_numeric_degree)))
                    )

                    e2_label = e2.get(
                        "display_label",
                        e2.get("roman_numeral", e2.get("root_degree", str(e2_numeric_degree)))
                    )

                    numeric_degree_transition = (
                        f"{e1_numeric_degree}->{e2_numeric_degree}"
                    )

                    roman_transition = (
                        f"{e1_label}→{e2_label}"
                    )

                    if methodology_id in ["vector_v1", "vector_v2"]:
                        vector_delta_x = obs.get("vector_delta_x")
                        vector_delta_y = obs.get("vector_delta_y")

                        if vector_delta_x is None or vector_delta_y is None:
                            unit_x = obs.get("vector_unit_x", 0)
                            unit_y = obs.get("vector_unit_y", 0)
                            strength = obs.get("strength_norm", obs.get("length_norm", 0))

                            vector_delta_x = unit_x * strength
                            vector_delta_y = unit_y * strength

                        # Vector exports use screen coordinates: +x points right, +y points down.
                        # For analysis display, brightness is inverted so positive means brighter/up.
                        # Stability follows the current line_v1 convention, where moving right lowers stability.
                        if methodology_id == "vector_v2":
                            delta_stability = obs.get("delta_arrival", vector_delta_x)
                            delta_brightness = obs.get("delta_valence", vector_delta_y)
                        else:
                            delta_stability = -vector_delta_x
                            delta_brightness = -vector_delta_y

                        start_stability = 0.5
                        end_stability = start_stability + delta_stability

                        start_brightness = 0.5
                        end_brightness = start_brightness + delta_brightness

                        plot_start_x = 0.5
                        plot_start_y = 0.5
                        plot_end_x = 0.5 + vector_delta_x
                        plot_end_y = 0.5 + vector_delta_y

                    else:
                        vector_delta_x = None
                        vector_delta_y = None

                        start_stability = 1 - obs["start_x_norm"]
                        end_stability = 1 - obs["end_x_norm"]
                        delta_stability = end_stability - start_stability

                        start_brightness = 1 - obs["start_y_norm"]
                        end_brightness = 1 - obs["end_y_norm"]
                        delta_brightness = end_brightness - start_brightness

                        plot_start_x = obs["start_x_norm"]
                        plot_end_x = obs["end_x_norm"]

                        plot_start_y = obs["start_y_norm"]
                        plot_end_y = obs["end_y_norm"]

                    row = {
                        "participant_id": participant_id,
                        "methodology_id": methodology_id,
                        "trial_id": trial_id,
                        "sample_set_id": get_sample_set_id(sample_id),
                        "sample_id": sample_id,

                        "audio_path": str(find_audio_file(sample_id)),                   

                        "degree_transition": roman_transition,
                        "numeric_degree_transition": numeric_degree_transition,
                        "chord_relationship": " | ".join(
                            build_chord_relationship_label(
                                sample["events"][i],
                                sample["events"][i + 1]
                            )
                            for i in range(len(sample["events"]) - 1)
                        ),

                        "start_stability": start_stability,
                        "end_stability": end_stability,
                        "delta_stability": delta_stability,

                        "start_brightness": start_brightness,
                        "end_brightness": end_brightness,
                        "delta_brightness": delta_brightness,

                        "perceptual_x_label": (
                            "Δ Arrival" if methodology_id == "vector_v2" else "Δ Stability"
                        ),
                        "perceptual_y_label": (
                            "Δ Valence" if methodology_id == "vector_v2" else "Δ Brightness"
                        ),
                        "perceptual_x_value": delta_stability,
                        "perceptual_y_value": delta_brightness,                        

                        "plot_start_x": plot_start_x,
                        "plot_end_x": plot_end_x,
                        "plot_start_y": plot_start_y,
                        "plot_end_y": plot_end_y,

                        "movement_dx": delta_stability,
                        "movement_dy": delta_brightness,

                        "vector_delta_x": vector_delta_x,
                        "vector_delta_y": vector_delta_y,
                        "strength_norm": obs.get("strength_norm"),

                        "delta_arrival": obs.get("delta_arrival"),
                        "delta_valence": obs.get("delta_valence"),

                        "length_norm": obs["length_norm"],
                        "angle_deg": obs["angle_deg"],

                        "event_1_notes_midi": e1.get("notes_midi", []),
                        "event_2_notes_midi": e2.get("notes_midi", []),
                        "event_1_notes_names": e1.get("notes_names", []),
                        "event_2_notes_names": e2.get("notes_names", []),
                        "event_1_inversion": e1.get("inversion"),
                        "event_2_inversion": e2.get("inversion"),
                        "event_1_chord_type": e1.get("chord_type"),
                        "event_2_chord_type": e2.get("chord_type"),

                        "temporal_integration_scale": temporal_integration_scale,
                        "duration_seconds": duration_seconds,
                        "temporal_integration_window_seconds": temporal_integration_window_seconds,
                        "temporal_integration_scale_description": temporal_integration_scale_description,                        

                    }

                    rows.append(row)

                    if VERBOSE and not printed_example:
                        print("       example joined row:")
                        print(f"         participant_id: {participant_id}")
                        print(f"         methodology_id: {methodology_id}")
                        print(f"         trial_id: {trial_id}")
                        print(f"         sample_id: {sample_id}")
                        print(
                            f"         sample_set_id: "
                            f"{get_sample_set_id(sample_id)}"
                        )
                        print(
                            f"         degree_transition: "
                            f"{roman_transition}"
                        )
                        print(
                            f"         length_norm: "
                            f"{obs['length_norm']:.3f}"
                        )

                        printed_example = True

                else:
                    missing_count += 1

                    if VERBOSE:
                        print(f"       MISSING SAMPLE: {sample_id}")

            total_count = len(mapping["mapping_observations"])

            if VERBOSE:
                print(
                    f"       matched samples: "
                    f"{matched_count}/{total_count}"
                )

    print(f"\nTotal joined rows: {len(rows)}")

    return rows

def export_joined_rows(rows):
    if not rows:
        print("No joined rows to export.")
        return
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved joined rows: {OUTPUT_PATH}")

def export_transition_summary(rows):
    transition_rows = build_transition_summary(rows)

    with open(TRANSITION_SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "degree_transition",
                "count",
                "avg_length_norm",
                "avg_delta_stability",
                "avg_delta_brightness"
            ]
        )
        writer.writeheader()
        writer.writerows(transition_rows)

    print(f"Saved transition summary: {TRANSITION_SUMMARY_PATH}")

def apply_filters(rows, filters=FILTERS):
    print("\n=== Active Filters ===")

    for key, value in filters.items():
        print(f"{key}: {value}")

    filtered_rows = []

    for row in rows:
        participant_filter = filters["participant_id"]
        methodology_filter = filters["methodology_id"]
        sample_set_filter = filters["sample_set_id"]
        temporal_scale_filter = filters.get(
            "temporal_integration_scale"
        )       
        trial_filter = filters.get("trial_id")

        if participant_filter is not None:
            if row["participant_id"] != participant_filter:
                continue

        if methodology_filter is not None:
            if row["methodology_id"] != methodology_filter:
                continue

        if sample_set_filter is not None:
            if isinstance(sample_set_filter, list):
                if row["sample_set_id"] not in sample_set_filter:
                    continue
            else:
                if row["sample_set_id"] != sample_set_filter:
                    continue

        if trial_filter is not None:
            if isinstance(trial_filter, list):
                if row["trial_id"] not in trial_filter:
                    continue
            else:
                if row["trial_id"] != trial_filter:
                    continue

        if temporal_scale_filter is not None:
            if row.get("temporal_integration_scale") != temporal_scale_filter:
                continue

        filtered_rows.append(row)

    print(f"Rows after filtering: {len(filtered_rows)}")

    return filtered_rows

def build_sample_summary(rows):
    sample_rows = []

    for row in rows:
        sample_rows.append({
            "participant_id": row["participant_id"],
            "methodology_id": row["methodology_id"],
            "trial_id": row["trial_id"],
            "sample_set_id": row["sample_set_id"],
            "sample_id": row["sample_id"],
            "degree_transition": row["degree_transition"],
            "chord_relationship": row["chord_relationship"],
            "length_norm": row["length_norm"],
            row.get("perceptual_x_label", "Δ Stability"): row.get(
                "perceptual_x_value",
                row["delta_stability"]
            ),
            row.get("perceptual_y_label", "Δ Brightness"): row.get(
                "perceptual_y_value",
                row["delta_brightness"]
            ),
        })

    return sample_rows

def export_sample_summary(rows):
    sample_rows = build_sample_summary(rows)

    with open(SAMPLE_SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(sample_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(sample_rows)

    print(f"Saved sample summary: {SAMPLE_SUMMARY_PATH}")

def build_transition_summary(rows):
    transition_stats = {}

    for row in rows:
        transition = row["degree_transition"]

        if transition not in transition_stats:
            transition_stats[transition] = {
                "count": 0,
                "total_length": 0,
                "total_delta_stability": 0,
                "total_delta_brightness": 0
            }

        transition_stats[transition]["count"] += 1
        transition_stats[transition]["total_length"] += row["length_norm"]
        transition_stats[transition]["total_delta_stability"] += row["delta_stability"]
        transition_stats[transition]["total_delta_brightness"] += row["delta_brightness"]

    transition_rows = []

    for transition, stats in transition_stats.items():
        avg_length = stats["total_length"] / stats["count"]
        avg_delta_stability = stats["total_delta_stability"] / stats["count"]
        avg_delta_brightness = stats["total_delta_brightness"] / stats["count"]

        transition_rows.append({
            "degree_transition": transition,
            "count": stats["count"],
            "avg_length_norm": round(avg_length, 3),
            "avg_delta_stability": round(avg_delta_stability, 3),
            "avg_delta_brightness": round(avg_delta_brightness, 3)
        })

    transition_rows = sorted(
        transition_rows,
        key=lambda row: row["avg_length_norm"],
        reverse=True
    )
    return transition_rows

def move_id_columns_to_end(rows):

    id_columns = [
        "participant_id",
        "methodology_id",
        "trial_id",
        "sample_set_id",
        "sample_id"
    ]

    display_rows = []

    for row in rows:

        new_row = {}

        for key, value in row.items():
            if key not in id_columns:
                new_row[key] = value

        for key in id_columns:
            if key in row:
                new_row[key] = row[key]

        display_rows.append(new_row)

    return display_rows

def make_compact_sample_table(rows):
    compact_rows = []

    for row in rows:
        compact_rows.append({
            "degree_transition": row["degree_transition"],
            "chord_relationship": row["chord_relationship"],
            "notes": (
                f"{row.get('event_1_notes_names')} → "
                f"{row.get('event_2_notes_names')}"
            ),
            "length_norm": row["length_norm"],
            row.get("perceptual_x_label", "Δ Stability"): row.get(
                "perceptual_x_value",
                row["delta_stability"]
            ),
            row.get("perceptual_y_label", "Δ Brightness"): row.get(
                "perceptual_y_value",
                row["delta_brightness"]
            ),
            "chord_type": (
                f"{row.get('event_1_chord_type')} → "
                f"{row.get('event_2_chord_type')}"
            ),
            "inversion": (
                f"{row.get('event_1_inversion')} → "
                f"{row.get('event_2_inversion')}"
            ),
            "sample_id": row["sample_id"]
        })

    return compact_rows


def build_ranked_sample_table(
    rows,
    metric_key,
    ranking_mode,
    limit
):
    ranked_rows = []

    for row in rows:
        value = row[metric_key]

        ranked_rows.append({
            **row,
            "ranking_value": value,
            "ranking_abs_value": abs(value)
        })

    if ranking_mode == "Highest Values":
        ranked_rows = sorted(
            ranked_rows,
            key=lambda row: row["ranking_value"],
            reverse=True
        )

    elif ranking_mode == "Lowest Values":
        ranked_rows = sorted(
            ranked_rows,
            key=lambda row: row["ranking_value"]
        )

    elif ranking_mode == "Absolute Magnitude":
        ranked_rows = sorted(
            ranked_rows,
            key=lambda row: row["ranking_abs_value"],
            reverse=True
        )

    ranked_rows = ranked_rows[:limit]

    compact_rows = []

    for row in ranked_rows:
        compact_rows.append({
            "degree_transition": row["degree_transition"],
            "chord_relationship": row["chord_relationship"],
            "ranking_value": round(
                row["ranking_value"],
                3
            ),
            "length_norm": round(
                row["length_norm"],
                3
            ),
            row.get("perceptual_x_label", "Δ Stability"): round(
                row.get("perceptual_x_value", row["delta_stability"]),
                3
            ),
            row.get("perceptual_y_label", "Δ Brightness"): round(
                row.get("perceptual_y_value", row["delta_brightness"]),
                3
            ),
            "movement_dx": round(
                row["movement_dx"],
                3
            ),
            "movement_dy": round(
                row["movement_dy"],
                3
            ),
            "chord_type": (
                f"{row.get('event_1_chord_type')} → "
                f"{row.get('event_2_chord_type')}"
            ),
            "inversion": (
                f"{row.get('event_1_inversion')} → "
                f"{row.get('event_2_inversion')}"
            ),
            "sample_id": row["sample_id"]
        })

    return compact_rows


def compute_line_trajectory_distance(row_a, row_b):
    start_dx = row_a["start_stability"] - row_b["start_stability"]
    start_dy = row_a["start_brightness"] - row_b["start_brightness"]

    end_dx = row_a["end_stability"] - row_b["end_stability"]
    end_dy = row_a["end_brightness"] - row_b["end_brightness"]

    start_distance = (start_dx ** 2 + start_dy ** 2) ** 0.5
    end_distance = (end_dx ** 2 + end_dy ** 2) ** 0.5

    return (start_distance + end_distance) / 2


def compute_full_vector_distance(row_a, row_b):
    dx = row_a["vector_delta_x"] - row_b["vector_delta_x"]
    dy = row_a["vector_delta_y"] - row_b["vector_delta_y"]

    return (dx ** 2 + dy ** 2) ** 0.5


def compute_perceptual_distance(row_a, row_b):
    methodology_a = row_a.get("methodology_id")
    methodology_b = row_b.get("methodology_id")

    if methodology_a != methodology_b:
        raise ValueError(
            "Cannot compute one topology from mixed methodologies yet. "
            "Select exactly one methodology before running topology analysis."
        )

    if methodology_a == "vector_v1":
        return compute_full_vector_distance(row_a, row_b)

    return compute_line_trajectory_distance(row_a, row_b)


# Backward-compatible name used by older grouping code.
def compute_trajectory_distance(row_a, row_b):
    return compute_perceptual_distance(row_a, row_b)


def mean_numeric(values):
    numeric_values = [
        value for value in values
        if isinstance(value, (int, float))
    ]

    if not numeric_values:
        return None

    return sum(numeric_values) / len(numeric_values)


def collapse_text_values(values):
    unique_values = sorted({
        value for value in values
        if value is not None
    })

    if not unique_values:
        return None

    if len(unique_values) == 1:
        return unique_values[0]

    return "MULTIPLE"


def get_topology_group_key(row, topology_unit):
    if topology_unit == "Observation":
        return None

    if topology_unit == "Participant-Sample":
        return (
            row.get("participant_id"),
            row.get("sample_id")
        )

    return (row.get("sample_id"),)


def aggregate_rows_for_topology(
    rows,
    topology_unit="Sample Aggregate"
):
    if topology_unit == "Observation":
        observation_rows = []

        for index, row in enumerate(rows, start=1):
            observation_rows.append({
                **row,
                "topology_unit": topology_unit,
                "topology_unit_id": f"obs_{index:05d}",
                "topology_label": row["sample_id"],
                "observation_count": 1,
                "participant_count": 1,
                "source_trial_count": 1,
                "source_sample_ids": row["sample_id"],
            })

        return observation_rows

    grouped = {}

    for row in rows:
        key = get_topology_group_key(row, topology_unit)

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(row)

    aggregate_rows = []

    numeric_keys = [
        "start_stability",
        "end_stability",
        "delta_stability",
        "start_brightness",
        "end_brightness",
        "delta_brightness",
        "plot_start_x",
        "plot_end_x",
        "plot_start_y",
        "plot_end_y",
        "movement_dx",
        "movement_dy",
        "vector_delta_x",
        "vector_delta_y",
        "strength_norm",
        "length_norm",
        "angle_deg",
        "duration_seconds",
        "temporal_integration_window_seconds",
    ]

    for key, group_rows in grouped.items():
        base_row = dict(group_rows[0])

        participant_ids = sorted({
            row.get("participant_id")
            for row in group_rows
            if row.get("participant_id") is not None
        })

        trial_ids = sorted({
            row.get("trial_id")
            for row in group_rows
            if row.get("trial_id") is not None
        })

        sample_ids = sorted({
            row.get("sample_id")
            for row in group_rows
            if row.get("sample_id") is not None
        })

        sample_id = collapse_text_values(sample_ids)
        participant_id = collapse_text_values(participant_ids)

        if topology_unit == "Participant-Sample":
            topology_unit_id = f"{participant_id}|{sample_id}"
            topology_label = f"{participant_id} / {sample_id}"
        else:
            topology_unit_id = str(sample_id)
            topology_label = str(sample_id)

        aggregate_row = {
            **base_row,
            "participant_id": participant_id,
            "trial_id": collapse_text_values(trial_ids),
            "sample_id": sample_id,
            "topology_unit": topology_unit,
            "topology_unit_id": topology_unit_id,
            "topology_label": topology_label,
            "observation_count": len(group_rows),
            "participant_count": len(participant_ids),
            "source_trial_count": len(trial_ids),
            "source_sample_ids": ", ".join(sample_ids),
        }

        for numeric_key in numeric_keys:
            aggregate_row[numeric_key] = mean_numeric([
                row.get(numeric_key)
                for row in group_rows
            ])

        aggregate_rows.append(aggregate_row)

    aggregate_rows = sorted(
        aggregate_rows,
        key=lambda row: row["topology_unit_id"]
    )

    return aggregate_rows


def build_distance_matrix(rows):
    methodologies = {row.get("methodology_id") for row in rows}

    if len(methodologies) > 1:
        raise ValueError(
            "Cannot build a topology from mixed methodologies yet. "
            "Select exactly one methodology."
        )

    matrix = []

    for row_a in rows:
        matrix_row = []

        for row_b in rows:
            distance = compute_perceptual_distance(
                row_a,
                row_b
            )

            matrix_row.append(distance)

        matrix.append(matrix_row)

    return matrix


def build_topology_embedding(
    rows,
    n_components=2,
    topology_unit="Sample Aggregate"
):
    topology_input_rows = aggregate_rows_for_topology(
        rows,
        topology_unit=topology_unit
    )

    if len(topology_input_rows) < 2:
        return [], 0.0

    distance_matrix = build_distance_matrix(topology_input_rows)

    mds = MDS(
        n_components=n_components,
        dissimilarity="precomputed",
        random_state=42
    )

    coords = mds.fit_transform(distance_matrix)

    stress = mds.stress_

    topology_rows = []

    for row, coord in zip(topology_input_rows, coords):
        topology_rows.append({
            **row,
            "topo_x": coord[0],
            "topo_y": coord[1]
        })

    return topology_rows, stress

def project_points_onto_axis(
    topology_rows,
    angle_deg
):
    theta = math.radians(angle_deg)

    ux = math.cos(theta)
    uy = math.sin(theta)

    projected_rows = []

    for row in topology_rows:

        position = (
            row["topo_x"] * ux +
            row["topo_y"] * uy
        )

        projected_rows.append({
            **row,
            "axis_position": position
        })

    return projected_rows


def safe_correlation(values_a, values_b):
    if len(values_a) < 2:
        return None

    if np.std(values_a) == 0:
        return None

    if np.std(values_b) == 0:
        return None

    return float(
        np.corrcoef(values_a, values_b)[0, 1]
    )


def compute_axis_correlations(
    topology_rows,
    angle_deg
):
    projected_rows = project_points_onto_axis(
        topology_rows,
        angle_deg
    )

    axis_positions = [
        row["axis_position"]
        for row in projected_rows
    ]

    axis_labels = get_perceptual_axis_labels(projected_rows[0])

    variables = {
        axis_labels["y_label"]: [
            row.get("perceptual_y_value", row["delta_brightness"])
            for row in projected_rows
        ],
        axis_labels["x_label"]: [
            row.get("perceptual_x_value", row["delta_stability"])
            for row in projected_rows
        ],
        "Length": [
            row["length_norm"]
            for row in projected_rows
        ],
    }

    correlation_rows = []

    for variable_name, values in variables.items():

        correlation = safe_correlation(
            axis_positions,
            values
        )

        correlation_rows.append({
            "variable": variable_name,
            "correlation": (
                None
                if correlation is None
                else round(correlation, 3)
            ),
            "abs_correlation": (
                None
                if correlation is None
                else round(abs(correlation), 3)
            )
        })

    correlation_rows = sorted(
        correlation_rows,
        key=lambda row: (
            -1
            if row["abs_correlation"] is None
            else row["abs_correlation"]
        ),
        reverse=True
    )

    return correlation_rows


def build_axis_correlation_curve(
    topology_rows,
    angle_step=1
):
    angle_rows = []

    for angle in range(0, 181, angle_step):

        correlation_rows = compute_axis_correlations(
            topology_rows,
            angle
        )

        row = {
            "angle": angle
        }

        for correlation_row in correlation_rows:
            variable = correlation_row["variable"]
            correlation = correlation_row["correlation"]

            row[variable] = correlation

        angle_rows.append(row)

    return angle_rows

def build_axis_correlation_curve_plot(
    topology_rows,
    use_absolute=True
):
    angle_rows = build_axis_correlation_curve(
        topology_rows
    )

    fig = go.Figure()

    variables = list(angle_rows[0].keys())
    variables.remove("angle")

    for variable in variables:

        y_values = []

        for row in angle_rows:
            value = row[variable]

            if value is None:
                y_values.append(None)
            elif use_absolute:
                y_values.append(abs(value))
            else:
                y_values.append(value)

        fig.add_trace(
            go.Scatter(
                x=[
                    row["angle"]
                    for row in angle_rows
                ],
                y=y_values,
                mode="lines",
                name=variable
            )
        )

    title = (
        "Axis Correlation by Angle (Absolute)"
        if use_absolute
        else "Axis Correlation by Angle (Signed)"
    )

    yaxis_range = (
        [0, 1]
        if use_absolute
        else [-1, 1]
    )

    fig.update_layout(
        title=title,
        xaxis_title="Axis Angle",
        yaxis_title=(
            "Absolute Correlation"
            if use_absolute
            else "Correlation"
        ),
        height=450,
        yaxis=dict(
            range=yaxis_range
        )
    )

    return fig

def build_latent_axis_point_cloud_plot(
    topology_rows,
    angle_deg
):
    fig = go.Figure()

    x_values = [
        row["topo_x"]
        for row in topology_rows
    ]

    y_values = [
        row["topo_y"]
        for row in topology_rows
    ]

    max_extent = max(
        max(abs(x) for x in x_values),
        max(abs(y) for y in y_values)
    )

    axis_limit = max_extent * 1.25

    theta = math.radians(angle_deg)

    ux = math.cos(theta)
    uy = math.sin(theta)

    line_length = axis_limit

    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker=dict(
                size=9,
                color="rgba(0,0,0,0)"
            ),
            name=" ",
            hoverinfo="skip",
            showlegend=True,
            visible="legendonly"
        )
    )

    fig.add_shape(
        type="line",
        x0=-line_length * ux,
        y0=-line_length * uy,
        x1= line_length * ux,
        y1= line_length * uy,
        line=dict(
            color="rgba(86,172,184,0.9)",
            width=2
        )
    )


    point_x = []
    point_y = []
    hover_texts = []
    sample_ids = []

    for row in topology_rows:
        point_x.append(row["topo_x"])
        point_y.append(row["topo_y"])
        sample_ids.append(row["topology_unit_id"])
        axis_labels = get_perceptual_axis_labels(row)

        hover_texts.append(
            f"{row['topology_label']}<br>"
            f"Unit: {row.get('topology_unit')}<br>"
            f"Observations: {row.get('observation_count', 1)}<br>"
            f"Participants: {row.get('participant_count', 1)}<br>"
            f"Transition: {row['degree_transition']}<br>"
            f"Length: {row['length_norm']:.3f}<br>"
            f"{axis_labels['x_label']}: {row['delta_stability']:.3f}<br>"
            f"{axis_labels['y_label']}: {row['delta_brightness']:.3f}"
        )

    fig.add_trace(
        go.Scatter(
            x=point_x,
            y=point_y,
            mode="markers",
            marker=dict(
                size=9,
                color="rgba(160,160,160,0.9)"
            ),
            customdata=sample_ids,
            hovertext=hover_texts,
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False
        )
    )

    fig.update_layout(
        xaxis_title="Embedding Coordinate A",
        yaxis_title="Embedding Coordinate B",
        height=500,
        showlegend=True,
        plot_bgcolor="#0a0a0a",
        paper_bgcolor="#0a0a0a",     
        margin=dict(
            l=60,
            r=20,
            t=40,
            b=60
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            itemclick=False,
            itemdoubleclick=False,
        )
    )


    fig.update_xaxes(
        showgrid=True,
        gridcolor="#2b2f3a",
        zeroline=False,
        fixedrange=True
    )

    fig.update_yaxes(
        showgrid=True,
        gridcolor="#2b2f3a",
        zeroline=False,
        scaleanchor="x",
        scaleratio=1,
        fixedrange=True
    )

    # fig = auto_zoom_topology_axes(
    #     fig,
    #     topology_rows,
    #     padding_ratio=0.18,
    #     min_half_range=0.08
    # )

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#0a0a0a",
        paper_bgcolor="#0a0a0a",
        hoverlabel=dict(
            bgcolor="#151515",
            font_color="#d0d0d0",
            bordercolor="#444444"
        )
    )

    fig.update_xaxes(
        gridcolor="#2b2f3a",
        linecolor="#2b2f3a",
    )

    fig.update_yaxes(
        gridcolor="#2b2f3a",
        linecolor="#2b2f3a",
    )

    fig = apply_topology_plot_theme(fig)

    fig = auto_zoom_topology_axes(
        fig,
        topology_rows,
        padding_ratio=0.22,
        min_half_range=0.12
    )

    return fig

def build_topology_point_cloud_plot(rows):
    topology_rows, stress = build_topology_embedding(rows)

    fig = go.Figure()

    for row in topology_rows:

        hover_text = (
            f"{row['sample_id']}<br>"
            f"Transition: {row['degree_transition']}<br>"
            f"Notes: "
            f"{row['event_1_notes_names']} → "
            f"{row['event_2_notes_names']}<br>"
            f"Length: {row['length_norm']:.3f}<br>"
            f"Δ Stability: {row['delta_stability']:.3f}<br>"
            f"Δ Brightness: {row['delta_brightness']:.3f}"
        )

        fig.add_trace(
            go.Scatter(
                x=[row["topo_x"]],
                y=[row["topo_y"]],
                mode="markers",
                marker=dict(
                    size=10,
                    color="rgba(160,160,160,0.9)"
                ),
                hovertemplate=(
                    hover_text
                    + "<extra></extra>"
                ),
                showlegend=False
            )
        )

    fig.update_layout(
        title="Click a point to hear its audio sample",
        xaxis_title="Topology Dimension 1",
        yaxis_title="Topology Dimension 2",
        font=dict(
            family="Arial, Helvetica, sans-serif",
            size=8,
            color="#d0d0d0"
        ),
        xaxis_title_font=dict(size=10),
        yaxis_title_font=dict(size=10),
        legend_font=dict(size=8),        
        height=500,
        showlegend=False
    )

    fig.update_xaxes(
        tickfont=dict(size=8),
        title_font=dict(size=10)
    )

    fig.update_yaxes(
        tickfont=dict(size=8),
        title_font=dict(size=10)
    )

    fig.update_xaxes(
        showgrid=True,
        zeroline=False
    )

    fig.update_yaxes(
        showgrid=True,
        zeroline=False,
        scaleanchor="x",
        scaleratio=1
    )

    fig = apply_topology_plot_theme(fig)

    return fig

def find_best_axis_angles(
    topology_rows,
    angle_step=1
):
    angle_rows = build_axis_correlation_curve(
        topology_rows,
        angle_step
    )

    variables = [
        key for key in angle_rows[0].keys()
        if key != "angle"
    ]

    best_rows = []

    for variable in variables:

        best_angle = None
        best_correlation = None
        best_abs_correlation = -1

        for row in angle_rows:
            correlation = row.get(variable)

            if correlation is None:
                continue

            abs_correlation = abs(correlation)

            if abs_correlation > best_abs_correlation:
                best_abs_correlation = abs_correlation
                best_correlation = correlation
                best_angle = row["angle"]

        best_rows.append({
            "variable": variable,
            "best_angle": best_angle,
            "correlation": best_correlation,
            "abs_correlation": round(best_abs_correlation, 3)
        })

    return best_rows

def build_clustered_topology_plot(
    topology_rows
):
    fig = go.Figure()

    group_ids = sorted(
        set(row["group_id"] for row in topology_rows)
    )

    for group_id in group_ids:

        group_rows = [
            row for row in topology_rows
            if row["group_id"] == group_id
        ]

        x_values = [
            row["topo_x"]
            for row in group_rows
        ]

        y_values = [
            row["topo_y"]
            for row in group_rows
        ]

        text_values = [
            row.get("topology_label", row["sample_id"]).split("_")[-1]
            for row in group_rows
        ]

        hover_values = []

        for row in group_rows:
            axis_labels = get_perceptual_axis_labels(row)
            hover_values.append(
                f"{row.get('topology_label', row['sample_id'])}<br>"
                f"{row['group_id']}<br>"
                f"Group size: {row['group_size']}<br>"
                f"Observations: {row.get('observation_count', 1)}<br>"
                f"Participants: {row.get('participant_count', 1)}<br>"
                f"Transition: {row['degree_transition']}<br>"
                f"Length: {row['length_norm']:.3f}<br>"
                f"{axis_labels['x_label']}: {row['delta_stability']:.3f}<br>"
                f"{axis_labels['y_label']}: {row['delta_brightness']:.3f}"
            )

        marker_style = dict(
            size=10
        )

        if group_id == "Ungrouped":
            marker_style = dict(
                size=8,
                color="rgba(120,120,120,0.55)"
            )

        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="markers",
                marker=marker_style,
                name=group_id,
                hovertext=hover_values,
                hovertemplate="%{hovertext}<extra></extra>"
            )
        )

    x_all = [
        row["topo_x"]
        for row in topology_rows
    ]

    y_all = [
        row["topo_y"]
        for row in topology_rows
    ]

    max_extent = max(
        max(abs(x) for x in x_all),
        max(abs(y) for y in y_all)
    )

    axis_limit = max_extent * 1.25

    fig.update_layout(
        xaxis_title="Embedding Coordinate A",
        yaxis_title="Embedding Coordinate B",
        height=500,
        showlegend=True,
        margin=dict(
            l=60,
            r=20,
            t=40,
            b=60
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )

    fig.update_xaxes(
        showgrid=True,
        zeroline=False,
        fixedrange=True
    )

    fig.update_yaxes(
        showgrid=True,
        zeroline=False,
        scaleanchor="x",
        scaleratio=1,
        fixedrange=True
    )

    fig = apply_topology_plot_theme(fig)

    fig = auto_zoom_topology_axes(
        fig,
        topology_rows,
        padding_ratio=0.22,
        min_half_range=0.12
    )

    return fig

def build_proximity_groups(rows, max_distance):
    groups = []
    used_sample_ids = set()

    for row in rows:
        sample_id = row["sample_id"]

        if sample_id in used_sample_ids:
            continue

        group = [row]
        used_sample_ids.add(sample_id)

        for other_row in rows:
            other_sample_id = other_row["sample_id"]

            if other_sample_id in used_sample_ids:
                continue

            distance = compute_trajectory_distance(
                row,
                other_row
            )

            if distance <= max_distance:
                group.append(other_row)
                used_sample_ids.add(other_sample_id)

        groups.append(group)

    return groups

def assign_proximity_group_ids(
    rows,
    max_distance
):
    groups = build_proximity_groups(
        rows,
        max_distance
    )

    grouped_rows = []

    group_counter = 1

    for group in groups:

        if len(group) == 1:
            group_id = "Ungrouped"
        else:
            group_id = f"Group {group_counter}"
            group_counter += 1

        for row in group:
            grouped_rows.append({
                **row,
                "group_id": group_id,
                "group_size": len(group)
            })

    return grouped_rows


def compute_topology_distance(row_a, row_b):
    dx = row_a["topo_x"] - row_b["topo_x"]
    dy = row_a["topo_y"] - row_b["topo_y"]

    return (dx ** 2 + dy ** 2) ** 0.5


def assign_topology_group_ids(
    topology_rows,
    max_distance
):
    visited_unit_ids = set()
    grouped_rows = []
    group_counter = 1

    row_lookup = {
        row["topology_unit_id"]: row
        for row in topology_rows
    }

    neighbors = {
        row["topology_unit_id"]: []
        for row in topology_rows
    }

    for i in range(len(topology_rows)):
        for j in range(i + 1, len(topology_rows)):

            row_a = topology_rows[i]
            row_b = topology_rows[j]

            distance = compute_topology_distance(
                row_a,
                row_b
            )

            if distance <= max_distance:
                neighbors[row_a["topology_unit_id"]].append(
                    row_b["topology_unit_id"]
                )
                neighbors[row_b["topology_unit_id"]].append(
                    row_a["topology_unit_id"]
                )

    for row in topology_rows:
        unit_id = row["topology_unit_id"]

        if unit_id in visited_unit_ids:
            continue

        stack = [unit_id]
        component_ids = []

        while stack:
            current_id = stack.pop()

            if current_id in visited_unit_ids:
                continue

            visited_unit_ids.add(current_id)
            component_ids.append(current_id)

            for neighbor_id in neighbors[current_id]:
                if neighbor_id not in visited_unit_ids:
                    stack.append(neighbor_id)

        if len(component_ids) == 1:
            group_id = "Ungrouped"
        else:
            group_id = f"Group {group_counter}"
            group_counter += 1

        group_size = len(component_ids)

        for component_id in component_ids:
            grouped_rows.append({
                **row_lookup[component_id],
                "group_id": group_id,
                "group_size": group_size
            })

    return grouped_rows


def get_topology_fidelity(stress):
    if stress < 0.05:
        return "Excellent"

    elif stress < 0.10:
        return "Good"

    elif stress < 0.20:
        return "Moderate"

    else:
        return "Poor"

def find_most_similar_pair(rows):

    best_distance = float("inf")
    best_pair = None

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):

            distance = compute_trajectory_distance(
                rows[i],
                rows[j]
            )

            if distance < best_distance:
                best_distance = distance

                best_pair = (
                    rows[i]["sample_id"],
                    rows[j]["sample_id"]
                )

    return {
        "sample_a": best_pair[0],
        "sample_b": best_pair[1],
        "distance": round(best_distance, 4)
    }

def main():
    rows = scan_archive()

    filtered_rows = apply_filters(rows)

    export_transition_summary(filtered_rows)
    export_joined_rows(filtered_rows)
    export_sample_summary(filtered_rows)

    plot_affect_trajectories(
        filtered_rows,
        OUTPUT_DIR
    )

    print(
        f"\nRows returned to main: "
        f"{len(filtered_rows)}"
    )

    return


if __name__ == "__main__":
    main()
