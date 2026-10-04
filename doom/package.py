"""Publish only the display ROM and media tied to a passing integration run."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
DOOM=ROOT/'doom'
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((DOOM/'build/display-report.json').read_text())
rom=DOOM/'receiver/build/doom-receiver.gbc'
if digest(rom)!=report['receiver_sha256'] or report['exact_pixelwise_frame_comparisons']<30:
    raise SystemExit('Display integration evidence is missing or stale; run make doom-test')
suffix='.dylib' if sys.platform=='darwin' else '.so'
matching={
    DOOM/'engine/build'/('libchromatic_doom'+suffix):report['engine_library_sha256'],
    DOOM/'engine/data/doom1.wad':report['iwad_sha256'],
    DOOM/'receiver/main.c':report['receiver_source_sha256'],
    **{DOOM/path:sha for path,sha in report['host_source_sha256'].items()},
}
if any(digest(path)!=sha for path,sha in matching.items()):
    raise SystemExit('Engine/receiver/host sources changed after validation; run make doom-test')
engine=json.loads((DOOM/'engine/build/headless-report.json').read_text())
if digest(DOOM/'engine/data/doom1.wad')!=engine['iwad_sha256'] or len(engine['results'])!=13:
    raise SystemExit('Engine validation evidence is missing or stale; run make doom-test')
for source,target in [(rom,ROOT/'roms/doom-display-client.gbc'),
                      (DOOM/'build/doom-receiver.gif',ROOT/'docs/doom-preview.gif'),
                      (DOOM/'build/doom-receiver-large.png',ROOT/'docs/doom-preview.png')]:
    shutil.copyfile(source,target)
report['engine_validation']=engine
report['physical_hardware']='Not tested; Mac USB access and matching experimental firmware are required'
report['audio']='Disabled'
report['published_media_sha256']={p.name:digest(p) for p in [ROOT/'docs/doom-preview.gif',ROOT/'docs/doom-preview.png']}
report['rtl_validation']={
    'upstream_commit':'0adf3822613a0230d18e0d73193f78337d1100b6',
    'scope':'Actual upstream VirtualCart/MBC RTL with modeled memory controller; no USB or physical board',
    'evidence':'See docs/doom-rtl-validation.txt for the separately executed optional test',
}
(ROOT/'docs/doom-validation.json').write_text(json.dumps(report,indent=2)+'\n')
(ROOT/'roms/SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted((ROOT/'roms').glob('*.gbc'))))
print(f'Packaged experimental display client: {digest(rom)}')
