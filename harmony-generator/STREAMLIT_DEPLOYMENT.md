# Deploy Affective Atlas as a second Community Cloud app

## Exact app settings

| Setting | Value |
|---|---|
| Repository | `mcbeth-ty/topo-audio-tools` |
| Branch | `main` |
| Main file path | `harmony-generator/affective_atlas_demo.py` |
| Python version (Advanced settings) | **3.12** |
| Required secrets | **None** |

1. Sign into https://share.streamlit.io/ and choose **Create app** / deploy from
   an existing GitHub repository.
2. Enter the settings above. Choose a new app URL, e.g. an available
   `affective-atlas` name. **Create a separate app**: do not edit the existing
   HSG app’s entry point, URL, Python version, or secrets.
3. Select Python **3.12** in Advanced settings, then deploy. Community Cloud
   uses `harmony-generator/requirements.txt`; root `packages.txt` installs
   `libfluidsynth3`. No browser audio device or MIDI player is required.
4. Verify Model 1 → Model 4 → Model 2, audio, Pathfinder, an example Arrange
   submission, and both Ambient Generator frameworks. The first sound request
   downloads/verifies the SoundFont once; it may take longer than later requests.

## Assets and privacy

The three explicitly curated public snapshots are checked into
`harmony-generator/public_data/models/` (about 357 KB combined). They contain
aliased node IDs, frozen Ordinal 3D-first/color coordinates, descriptive tags,
aggregated relationship links, and exact 15-second rendering recipes. They do not
contain original study/stimulus UUIDs, raw submitted trials, participant details,
research timestamps, local filesystem paths, or private library records.

All research libraries, studies, other saved models, private audit reports,
virtual environments, credentials, temporary files, and generated archives/audio
remain uncommitted. The original local datasets are not rewritten. To explicitly
republish the same three named snapshots after research changes:

```sh
python harmony-generator/tools/build_public_models.py
```

Review the resulting public JSON diff before committing. This export is not run
by the deployed app and never modifies its source research data.

The SoundFont is **not** committed. `atlas_assets.py` fetches a pinned version of
GeneralUser GS from its official GitHub packaging source, checks the exact size
and SHA-256, and atomically caches it in the OS temporary directory. The author’s
license and attribution are in `third_party/`. No manual external audio hosting
or Git LFS is needed, but the app needs outbound HTTPS to raw.githubusercontent.com
for that first download. Subsequent synthesis stays entirely in the app.

Optional host environment overrides (not needed for the normal deployment):

- `AMBIENT_SF2_PATH`: a pre-provisioned GeneralUser GS file with the documented hash.
- `AFFECTIVE_ATLAS_ASSET_CACHE`: writable cache directory outside the repository.
- `AFFECTIVE_ATLAS_MODELS_DIR`: directory containing explicitly selected public
  `model 1`, `model 4`, `model 2` JSON snapshots. Defaults to the packaged assets.

Do not set `TOPO_AUDIO_DEMO` for this new app; that flag belongs to the existing
HSG deployment. The dedicated Affective Atlas entry point does not depend on it.

## Existing HSG and research application

`harmony-generator/app.py` remains the existing HSG entry point, with the existing
`TOPO_AUDIO_DEMO` behavior. The full app offers the Ambient research workspace
when demo restrictions are off. Native audio dependencies are additive; they do
not replace HSG generation or its public demo. The repository-root dependency
file and the existing keep-awake workflow are preserved.

Private research state is intentionally not deployed. Community Cloud storage
is ephemeral, so it must not be treated as a persistent research collection.
The public entry point does not write Arrange judgments or any other research
state; only memory, Streamlit session media, and the external asset cache are used.

## Local and Linux checks

From the repository root:

```sh
python -m pip install -r harmony-generator/requirements.txt
# Linux/Debian only: sudo apt-get install libfluidsynth3
# macOS native dependency, if missing: brew install fluid-synth
python -m streamlit run harmony-generator/affective_atlas_demo.py \
  --server.address 127.0.0.1 --server.port 8502
```

No Mac home-directory paths are required. Open http://127.0.0.1:8502.

```sh
python harmony-generator/tools/verify_cloud_demo.py
python -m unittest discover -s harmony-generator -p 'test_*.py'
node harmony-generator/test_ambient_pathfinder.mjs
```

The **Affective Atlas Linux checks** GitHub Actions workflow performs these on
Ubuntu/Python 3.12, including a cold asset download and real offline FluidSynth.
Check its status for the pushed commit before deploying. Local macOS verification
alone is not claimed as a Linux runtime test.

## Later embedding

After verifying the separate public URL, an iframe can point at
`https://YOUR-NEW-APP.streamlit.app/?embed=true` (use `&embed=true` if it already
has query parameters). The layout is responsive and playback requires user
interaction. No topo.audio changes are part of this task.

References:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app/embed-your-app
