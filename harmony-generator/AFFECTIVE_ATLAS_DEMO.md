# Affective Atlas public demo

A separate entry point presents Model 1 → Model 4 → Model 2, guided Pathfinder,
a browser-local Arrange example, and four-sample Ambient generation.

From the repository root, in the Python environment running Streamlit:

```sh
python -m pip install -r harmony-generator/requirements.txt
python -m streamlit run harmony-generator/affective_atlas_demo.py \
  --server.address 127.0.0.1 --server.port 8502
```

Open http://127.0.0.1:8502. FluidSynth must be installed natively (`libfluidsynth3`
on Debian, `brew install fluid-synth` on macOS). GeneralUser GS is downloaded
lazily from a pinned official source and verified/cached outside the repository;
optionally set `AMBIENT_SF2_PATH` to an existing matching asset.

Only sanitized snapshots from `public_data/models/` are loaded by default. The
private library, raw trials, source UUIDs, local paths and other saved models are
not shipped. No audio blobs or large sample libraries are committed.

The generator uses Expanded vocabulary, four 15-second Warm Pad sounds, Room
reverb at .60, and fixed state weights 25/100/100. Numeric register defaults to
48–72 (bounds 24–96). Cards show voices, states, initial harmony and notes.
Public text uses sans-serif except map labels and the generator control panel.

Arrange submissions stay in the browser. Model navigation, tutorials and tag
visibility are per-visit; lower introductions are scroll-triggered. Reduced-motion
preferences are respected. The existing shared rendering, audio, generation,
classification and Pathfinder algorithms are reused with explicit public UI flags.
No 5-second or researcher-only controls are exposed. Session-local callbacks have
no routes to research save, submit, export or destructive operations.

The existing `app.py` and `TOPO_AUDIO_DEMO` deployment remain separate.
See [STREAMLIT_DEPLOYMENT.md](STREAMLIT_DEPLOYMENT.md) for exact Community Cloud
settings, asset provenance, tests, and future embedding instructions.
