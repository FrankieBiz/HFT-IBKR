"""Build a deterministic standard-library Python zip application, without downloads."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
ENTRY='''import sys
if len(sys.argv)<2 or sys.argv[1] not in ('research','control','local','data','view','session'):
    print('Usage: python3 quant-system.pyz {research|control|local|data|view|session} COMMAND [OPTIONS]',file=sys.stderr)
    sys.exit(2)
command=sys.argv.pop(1)
if command=='research':
    from quant_research.__main__ import main
elif command=='control':
    from quant_control.__main__ import main
elif command=='local':
    from quant_local.__main__ import main
elif command=='data':
    from quant_data.__main__ import main
elif command=='session':
    from quant_session.__main__ import main
else:
    from quant_view.__main__ import main
sys.exit(main())
'''


def build(destination):
    # Only explicit source packages are included; no local data, journals or secrets.
    sources={'__main__.py':ENTRY.encode()}
    for package in ('quant_research','quant_control','quant_local','quant_data','quant_view','quant_session'):
        for path in sorted((ROOT/package).glob('*.py')):
            sources[f'{package}/{path.name}']=path.read_bytes()
    buffer=io.BytesIO()
    with ZipFile(buffer,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for name,content in sorted(sources.items()):
            info=ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,content,compresslevel=9)
    content=buffer.getvalue()
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp')
    try:
        with temporary.open('wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary,destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {'artifact':str(destination),'sha256':hashlib.sha256(content).hexdigest(),
            'source_files':len(sources),'runtime_dependencies':'Python standard library'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'dist/quant-system.pyz')
    print(json.dumps(build(parser.parse_args().output),indent=2))
