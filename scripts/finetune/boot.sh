#!/usr/bin/env bash
# The GPU job's container command. Waits for the payload (copied in over SSH to the host,
# then `docker cp`), unpacks it to /work, runs, and holds so /work/out can be copied out.
set -uo pipefail
mkdir -p /work/out
echo "BOOT waiting for payload"
for _ in $(seq 1 360); do [ -f /work/payload.tgz.done ] && break; sleep 5; done
[ -f /work/payload.tgz.done ] || { echo "BOOT no payload after 30 min"; exit 1; }
tar xzf /work/payload.tgz -C /
bash /work/run.sh 2>&1 | tee /work/out/run.log
echo "exit ${PIPESTATUS[0]}" > /work/out/DONE
echo "BOOT done; holding for copy-out"
sleep "${HOLD:-1800}"
