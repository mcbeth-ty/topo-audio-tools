"""Portable, lazy public-demo SoundFont provisioning; never writes research data."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

from ambient_soundfont import SoundFontUnavailable, soundfont_identity

SOUNDFONT_COMMIT='684543d5e5efaef08d02be50dcda8d552478fa60'
SOUNDFONT_URL=f'https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/{SOUNDFONT_COMMIT}/GeneralUser-GS.sf2'
SOUNDFONT_SHA256='9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'
SOUNDFONT_BYTES=32319396


@contextmanager
def _download_lock(directory):
    with (directory/'.download.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def demo_soundfont():
    """Use a verified override or a pinned upstream SF2 cached outside the repo."""
    configured=os.environ.get('AMBIENT_SF2_PATH')
    if configured:
        identity=soundfont_identity(configured)
        if identity[1]!=SOUNDFONT_SHA256:raise SoundFontUnavailable('The configured SoundFont differs from the demo sound library.')
        return identity
    directory=Path(os.environ.get('AFFECTIVE_ATLAS_ASSET_CACHE',str(Path(tempfile.gettempdir())/'affective-atlas-assets'))).expanduser()
    directory.mkdir(parents=True,exist_ok=True)
    destination=directory/'GeneralUser-GS.sf2'
    with _download_lock(directory):
        if destination.is_file():
            identity=soundfont_identity(str(destination))
            if identity[1]==SOUNDFONT_SHA256:return identity
        descriptor,temporary=tempfile.mkstemp(prefix='.soundfont-',dir=directory)
        try:
            digest=hashlib.sha256();size=0
            request=urllib.request.Request(SOUNDFONT_URL,headers={'User-Agent':'AffectiveAtlas/1.0'})
            with os.fdopen(descriptor,'wb') as target,urllib.request.urlopen(request,timeout=60) as response:
                while block:=response.read(1024*1024):
                    size+=len(block)
                    if size>SOUNDFONT_BYTES:raise ValueError('Unexpected SoundFont size.')
                    target.write(block);digest.update(block)
                target.flush();os.fsync(target.fileno())
            if size!=SOUNDFONT_BYTES or digest.hexdigest()!=SOUNDFONT_SHA256:raise ValueError('SoundFont verification failed.')
            os.replace(temporary,destination)
        except (OSError,ValueError) as error:
            raise SoundFontUnavailable('The demo sound library could not be downloaded or verified. Retry, or configure AMBIENT_SF2_PATH with the documented GeneralUser GS asset.') from error
        finally:Path(temporary).unlink(missing_ok=True)
    return soundfont_identity(str(destination))
