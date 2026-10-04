"""Bounded local probes; no model loading, installation or broker access."""

import csv
from datetime import datetime, timezone
from importlib import metadata
import io
import json
import os
import platform
import subprocess
import sys

GIB = 1024 ** 3
POLICY = {'min_ram_bytes': 28 * GIB, 'min_gpu_total_bytes': 15 * GIB // 2,
          'min_gpu_free_bytes': 4 * GIB, 'python_min': [3, 12], 'python_max': [3, 14]}

CUDA_PROBE = '''
import json, sys
try:
    import torch
    index = int(sys.argv[1])
    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA unavailable; check wheel and driver")
    if index >= torch.cuda.device_count():
        raise RuntimeError("GPU index outside PyTorch visible devices")
    torch.cuda.set_device(index)
    with torch.inference_mode():
        tensor = torch.tensor([1.0, 2.0, 3.0], device=f"cuda:{index}", dtype=torch.float32)
        result = tensor.sum().item()
        del tensor
    torch.cuda.synchronize(index)
    torch.cuda.empty_cache()
    free, total = torch.cuda.memory.mem_get_info(index)
    print(json.dumps({"ok": True, "device_index": index,
        "device_name": torch.cuda.get_device_name(index),
        "torch_version": str(torch.__version__), "cuda_version": torch.version.cuda,
        "total_bytes": total, "free_bytes": free,
        "capability": list(torch.cuda.get_device_capability(index)),
        "bf16_supported": bool(torch.cuda.is_bf16_supported()), "smoke_result": result}, allow_nan=False))
except Exception as error:
    print(json.dumps({"ok": False, "error": type(error).__name__ + ": " + str(error)[:300]}))
'''


def run_probe(command, *, timeout):
    """Run a fixed argument list with a deadline; never invoke a shell."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {'ok': False, 'error': 'probe executable missing'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': f'probe timed out after {timeout} seconds'}
    except (OSError, UnicodeError) as error:
        return {'ok': False, 'error': type(error).__name__}
    if result.returncode != 0:
        return {'ok': False, 'error': f'probe exited {result.returncode}'}
    return {'ok': True, 'stdout': result.stdout}


def parse_inventory(content):
    devices = []
    for row in csv.reader(io.StringIO(content), skipinitialspace=True):
        if len(row) != 5:
            raise ValueError('invalid NVIDIA inventory row')
        index, name, driver, total, free = [value.strip() for value in row]
        index, total, free = int(index), int(total), int(free)
        if index < 0 or total <= 0 or not 0 <= free <= total or not name or not driver:
            raise ValueError('invalid NVIDIA inventory values')
        if any(device['index'] == index for device in devices):
            raise ValueError('duplicate NVIDIA index')
        devices.append({'index': index, 'name': name, 'driver': driver,
                        'total_mib': total, 'free_mib': free})
    if not devices:
        raise ValueError('empty NVIDIA inventory')
    return devices


def package_versions():
    versions = {}
    for name in ('torch', 'laya', 'transformers', 'huggingface-hub', 'nautilus_trader'):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def ram_bytes():
    try:
        pages, size = os.sysconf('SC_PHYS_PAGES'), os.sysconf('SC_PAGE_SIZE')
        if pages > 0 and size > 0:
            return pages * size
    except (AttributeError, OSError, ValueError):
        pass
    if platform.system() == 'Darwin':
        result = run_probe(['/usr/sbin/sysctl', '-n', 'hw.memsize'], timeout=5)
        if result['ok']:
            try:
                value = int(result['stdout'].strip())
                return value if value > 0 else None
            except ValueError:
                pass
    return None


def collect(*, gpu_index=0, skip_cuda=False):
    if type(gpu_index) is not int or gpu_index < 0:
        raise ValueError('gpu_index must be a nonnegative integer')
    packages = package_versions()
    inventory = run_probe(['nvidia-smi',
                          '--query-gpu=index,name,driver_version,memory.total,memory.free',
                          '--format=csv,noheader,nounits'], timeout=5)
    if inventory['ok']:
        try:
            inventory = {'ok': True, 'devices': parse_inventory(inventory['stdout'])}
        except ValueError:
            inventory = {'ok': False, 'error': 'malformed NVIDIA inventory'}
    if skip_cuda:
        cuda = {'skipped': True}
    elif not packages.get('torch'):
        cuda = {'ok': False, 'error': 'PyTorch distribution not installed in this interpreter'}
    else:
        probe = run_probe([sys.executable, '-I', '-c', CUDA_PROBE, str(gpu_index)], timeout=30)
        cuda = probe
        if probe['ok']:
            try:
                def reject_constant(value):
                    raise ValueError('non-finite JSON value')
                cuda = json.loads(probe['stdout'], parse_constant=reject_constant)
                if not isinstance(cuda, dict):
                    raise ValueError('CUDA probe must produce an object')
            except (ValueError, TypeError):
                cuda = {'ok': False, 'error': 'malformed CUDA probe output'}
    return {'system': platform.system(), 'release': platform.release(),
            'python': list(sys.version_info[:3]), 'ram_bytes': ram_bytes(),
            'packages': packages, 'gpu_index': gpu_index, 'nvidia': inventory, 'cuda': cuda}


def assess(evidence):
    """Required evidence must be present and valid; no model-readiness assertion."""
    checks = []

    def check(name, passed, reason):
        checks.append({'id': name, 'passed': bool(passed), 'detail': reason})

    check('platform', evidence.get('system') == 'Linux',
          'Combined stack targets native Linux or Linux under WSL2; other OS paths unverified.')
    version = evidence.get('python')
    valid_version = (isinstance(version, list) and len(version) == 3
                     and all(type(n) is int and n >= 0 for n in version))
    check('python', valid_version and [3, 12] <= version[:2] <= [3, 14],
          'Combined-stack study requires Python 3.12–3.14; diagnostic itself supports 3.11+.')
    ram = evidence.get('ram_bytes')
    check('ram', type(ram) is int and ram >= POLICY['min_ram_bytes'],
          'Require at least 28 GiB OS-visible RAM; guest/container allowances need separate review.')
    packages = evidence.get('packages')
    packages = packages if isinstance(packages, dict) else {}
    for name in ('torch', 'laya'):
        check(name, isinstance(packages.get(name), str) and bool(packages[name].strip()),
              f'{name} must be installed in the invoking Python environment; compatibility still untested.')
    cuda = evidence.get('cuda')
    cuda = cuda if isinstance(cuda, dict) else {}
    capability = cuda.get('capability')
    cuda_valid = (cuda.get('ok') is True and type(cuda.get('device_index')) is int
                  and type(evidence.get('gpu_index')) is int
                  and cuda['device_index'] == evidence['gpu_index'] >= 0
                  and isinstance(cuda.get('device_name'), str) and bool(cuda['device_name'].strip())
                  and isinstance(cuda.get('cuda_version'), str) and bool(cuda['cuda_version'])
                  and isinstance(cuda.get('torch_version'), str)
                  and cuda['torch_version'] == packages.get('torch')
                  and type(cuda.get('bf16_supported')) is bool
                  and isinstance(capability, list) and len(capability) == 2
                  and all(type(n) is int and n >= 0 for n in capability)
                  and type(cuda.get('smoke_result')) in (int, float) and cuda['smoke_result'] == 6.0)
    check('cuda', cuda_valid, 'Selected logical CUDA device must complete a real FP32 tensor operation.')
    total, free = cuda.get('total_bytes'), cuda.get('free_bytes')
    memory_valid = type(total) is int and type(free) is int and 0 <= free <= total
    check('gpu_memory', cuda_valid and memory_valid
          and total >= POLICY['min_gpu_total_bytes'] and free >= POLICY['min_gpu_free_bytes'],
          'Project budget: >=7.5 GiB total and >=4 GiB free VRAM; not a measured model requirement.')
    blockers = [item for item in checks if not item['passed']]
    return {'schema_version': 1, 'collected_at_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'blocked' if blockers else 'ready_for_model_benchmark',
            'model_benchmark_run': False, 'policy': POLICY.copy(), 'evidence': evidence,
            'checks': checks, 'blockers': blockers,
            'limitations': [
                'No checkpoint loaded; no Laya accuracy, peak memory or inference latency measured.',
                'Installed versions are inventory, not a tested dependency lock.',
                'Memory is a point-in-time observation; other workloads can change availability.',
                'NVIDIA inventory indices are not mapped to PyTorch logical device indices.',
                'No strategy profitability, paper readiness or live readiness is established.',
            ]}
