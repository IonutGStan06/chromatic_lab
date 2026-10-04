"""Package only a ROM with a passing, matching emulator validation report."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROM=ROOT/'build/chromatic-arcade.gbc'
report=json.loads((ROOT/'build/playtest/results.json').read_text())
digest=hashlib.sha256(ROM.read_bytes()).hexdigest()
assert report['sha256']==digest and len(report['checks'])==8
assert all(c['outcome']=='passed' for c in report['checks'])
(ROOT/'roms').mkdir(exist_ok=True)
shutil.copyfile(ROM,ROOT/'roms/chromatic-arcade.gbc')
(ROOT/'roms/SHA256SUMS').write_text(''.join(
    f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
    for p in sorted((ROOT/'roms').glob('*.gbc'))))
shutil.copyfile(ROOT/'build/arcade-preview.png',ROOT/'docs/arcade-preview.png')
shutil.copyfile(ROOT/'build/playtest/results.json',ROOT/'docs/validation.json')
with zipfile.ZipFile(ROOT/'build/chromatic-lab-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
    paths=[ROOT/name for name in ['.gitignore','Makefile','README.md','LICENSE','requirements-dev.txt']]
    for directory in ['src','tools','docs','roms','doom']:
        paths.extend(p for p in (ROOT/directory).rglob('*')
                     if p.is_file() and not {'__pycache__','build'}.intersection(p.relative_to(ROOT).parts))
    for path in sorted(paths): archive.write(path,Path('chromatic_lab')/path.relative_to(ROOT))
print(f'Packaged {ROM.stat().st_size} byte ROM; SHA-256 {digest}')
print('Source archive: build/chromatic-lab-source.zip')
