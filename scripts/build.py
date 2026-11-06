"""Build a portable Enigma2 plugin tarball using only Python 3."""
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'dist'
out.mkdir(exist_ok=True)
archive = out / 'enigma2-plugin-extensions-iptvpl-1.1.0.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    for source in sorted((root / 'Plugins/Extensions/IPTVPL').glob('*.py')):
        tar.add(source, arcname='usr/lib/enigma2/python/Plugins/Extensions/IPTVPL/' + source.name)
print(archive)

