# Loom Firecracker Hardware-Validation Implementation Patch

Apply these files to the repository root.

## Replaced files
- `.env.example`
- `loom/sandbox/factory.py`
- `loom/sandbox/firecracker_sandbox.py`
- `tests/test_firecracker_sandbox.py`

## Added files
- `loom/sandbox/firecracker_vm.py`
- `loom/sandbox/firecracker_worker.py`
- `loom/sandbox/firecracker_guest_agent.py`
- `tests/test_firecracker_factory.py`
- `tests/test_firecracker_guest_agent.py`
- `scripts/validate_firecracker_host.sh`
- `scripts/e2e_firecracker_validation.sh`
- `infra/firecracker/VERSION`
- `infra/firecracker/SHA256SUM`
- `infra/firecracker/README.md`
- `infra/firecracker/guest-agent.service`
- `infra/firecracker/loom-firecracker-worker.service`
- `infra/firecracker/install_guest_agent.sh`

## Important deployment gate
`infra/firecracker/SHA256SUM` intentionally contains a placeholder. Replace it with the SHA-256 of the exact deployed Firecracker v1.16.1 x86_64 binary before using `scripts/validate_firecracker_host.sh`.

The VM runner intentionally disables networking unless an explicit host/tap policy is implemented. The worker rejects network-enabled Tier C requests rather than silently opening egress. Production also enforces org-scoped repository roots by default.

The real Linux/KVM boot, isolation, cleanup, crash-recovery and concurrency phases still require a Linux host with `/dev/kvm`; they were not executed in this environment. Before deployment, replace the placeholder Firecracker SHA256, build the immutable kernel/rootfs, and install the worker/guest-agent systemd units. The guest agent also rejects symlink/device/FIFO archive members and uses a sanitized inherited environment.
