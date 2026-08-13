# Loom Firecracker runtime

The hardware validation plan treats the kernel and rootfs as immutable deployment artifacts. This directory contains the guest-agent contract and runtime pinning metadata; the actual `vmlinux` and `rootfs.ext4` images are deployment artifacts and must not be committed to Git.

## Certified runtime baseline

- Firecracker: `v1.16.1`
- Host architecture: `x86_64`
- Host kernel validation: follow Firecracker's supported-kernel policy
- Guest kernel: must expose virtio-vsock and virtio-blk to Loom's guest agent

Populate `SHA256SUM` with the SHA-256 of the exact deployed Firecracker binary before enabling production startup. The worker must fail closed when the approved version/hash is missing or mismatched.

Repository isolation: production defaults to `LOOM_FIRECRACKER_ENFORCE_ORG_ROOT=true`, so repositories must live below `${LOOM_FIRECRACKER_REPO_ROOT}/{org_id}/...`.
