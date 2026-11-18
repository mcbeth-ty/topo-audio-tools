"""Headless cloud smoke test: packaged models, native SoundFont, and generation."""
import hashlib
import io
from pathlib import Path
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from atlas_demo import load_demo_models,recipe_audio,generate_demo
from atlas_assets import demo_soundfont


def check_wav(wav):
    with wave.open(io.BytesIO(wav)) as audio:
        assert audio.getnchannels()==2
        assert 15<=audio.getnframes()/audio.getframerate()<=45.1
        assert audio.getsampwidth()==2


def main():
    private=ROOT/'data'
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in private.rglob('*') if p.is_file()}
    models=load_demo_models()
    assert [len(model[0]['ids']) for model in models]==[24,49,24]
    for public,recipes in models:
        assert all(len(p)==4 for p in public['world_positions'].values())
        for recipe in recipes.values():
            assert recipe['rendering']['duration_seconds']==15
            assert recipe['rendering']['soundfont']['program']==89
    font=demo_soundfont();print('Verified GeneralUser GS:',font[1],flush=True)
    for public,recipes in models:check_wav(recipe_audio(recipes[public['ids'][0]]))
    for framework in ('chromatic','chord_targeting'):
        result=generate_demo({'framework':framework})
        assert len(result)==4
        for stimulus,wav in result:
            assert stimulus['selection_settings']['harmonic_vocabulary']=='Expanded'
            check_wav(wav)
    after={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in private.rglob('*') if p.is_file()}
    assert before==after,'Demo changed private research data.'
    print('PASS: three packaged models, 15-second stereo SoundFont audio, both four-sample frameworks, and no research writes.',flush=True)


if __name__=='__main__':main()
