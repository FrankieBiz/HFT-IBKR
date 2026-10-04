# Local ML preflight design

Scope authorized by the user's request to choose the next step and start work.
H0 is split into an environment diagnostic now and a model benchmark later.

## Choice and alternatives

Build a standard-library diagnostic that runs on the target workstation and in
the portable archive. Installing Laya here would test the wrong computer and
download unnecessary weights. Building a broker adapter first would leave the
data and target-environment prerequisites unresolved. Historical calibration
remains the critical path, but needs a reviewed real dataset not present here.

## Contract

`python3 -m quant_local preflight --output PATH` writes a versioned JSON report.
It installs nothing, loads no checkpoints, opens no network connections and
does not import Laya. It reads installed distribution metadata and queries
`nvidia-smi` if available. CUDA is tested in a bounded isolated Python child
using installed PyTorch; a small FP32 tensor operation must complete correctly.
`--skip-cuda` records an unperformed check and can never pass readiness.
`--gpu-index N` selects the logical PyTorch device, not the nvidia-smi index;
CUDA visibility remapping must not match these indices implicitly.

The report contains OS/Python, OS-visible total RAM, dependency versions, driver
inventory without UUIDs/account data, CUDA device name/capability, actual free
and total memory, BF16 support, check outcomes, blockers and limitations.
Use Linux/WSL2 and Python 3.12–3.14 for this proposed combined stack. Project
preflight budgets are 28 GiB host RAM, 7.5 GiB device memory and 4 GiB free device
memory. These are conservative deployment budgets, not measured Laya requirements.
GPU memory is measured after the tiny smoke operation releases its tensors.
Nvidia-smi inventory is advisory; functional PyTorch evidence is authoritative.

Any missing, malformed, timed-out or failed required measurement blocks the
result. Installed Laya and PyTorch are required, but package presence does not
prove their compatibility or the accuracy/speed of a model. Status may be only
`blocked` or `ready_for_model_benchmark`, never trading/model readiness.
CPU fallback cannot pass a CUDA check. Reported RAM is not a container allowance;
WSL2 reports memory visible to its Linux guest rather than necessarily all host RAM.

Exit 0: all environment gates passed. Exit 2: blockers, invalid CLI input or
publication failure. A blocked report is still written for diagnosis. Outputs
must have an existing parent directory and may not overwrite an existing file
or symlink. Atomic publication follows the existing research report helper.
All subprocesses have finite deadlines; no shell execution or GPU reconfiguration.

## Components and verification

`quant_local/preflight.py`: bounded probes, metadata, parsing and pure assessment.
`quant_local/__main__.py`: CLI and atomic report publication.
`scripts/build.py`: include the package and `local` command in the archive.
Tests cover bad evidence, missing packages/CUDA, unknown RAM, unsupported OS,
low resources, explicit skip, device mismatch, timeouts and non-overwriting
reports. The archive must run the command outside the checkout. Real CUDA and
model memory/latency on the user's GPU remain outstanding.

Primary API references checked 2026-10-04:
[NVIDIA query interface](https://docs.nvidia.com/deploy/nvidia-smi/),
[PyTorch CUDA API](https://docs.pytorch.org/docs/stable/cuda.html).
Dependencies are isolated from existing research/control imports.
