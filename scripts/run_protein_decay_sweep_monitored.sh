#!/usr/bin/env bash
# Monitored launch of the hardened L2.2 sweep for a single process, with an
# external RSS ceiling watchdog. This does NOT modify sweep.py/the runner's
# own behavior -- it is a pure external supervisor: it launches the existing
# `scripts/l22_evidence/sweep.py run` unmodified, polls the RSS of that
# process and all its descendants (the actual runner subprocess lives one
# level down), and safely SIGTERMs (then SIGKILLs if needed) the whole
# process group if total RSS exceeds the ceiling -- mirroring the same
# proactive-stop discipline the two prior manual terminations used, but
# automated and logged.
#
# E1 (scope-C1 follow-up): every poll sample is ALSO appended to a tracked
# JSONL diagnostic (one compact JSON object per line, so an abrupt SIGKILL
# never leaves an unparseable half-written JSON array). This replaces the
# prior behavior of only writing to an untracked/scratch `.log` file --
# the Phase-1 ProteinDecay run's RSS trace (~0.60-0.64 GiB plateau,
# reported to the operator) was never persisted anywhere tracked and is
# NOT reconstructed here; this mechanism only captures timeseries data for
# runs launched after this change.
#
# Usage: bash scripts/run_protein_decay_sweep_monitored.sh <process> <ceiling_gib> <poll_s> <report_out> <rss_trace_out>
set -uo pipefail

PROCESS="${1:?process name required, e.g. ProteinDecay}"
CEILING_GIB="${2:-20}"
POLL_S="${3:-15}"
REPORT_OUT="${4:-docs/phase_f/l2_2_design_a/sweep_report_proteindecay.json}"
RSS_TRACE_OUT="${5:-docs/phase_f/l2_2_design_a/rss_diagnostics/${PROCESS}_rss_timeseries.jsonl}"
CEILING_KB=$(( CEILING_GIB * 1024 * 1024 ))
LOG_FILE="artifacts_sweep_monitor_${PROCESS}.log"

cd /mnt/e/opencell-worktrees/l22-proteindecay-memory
source /mnt/e/opencell/.venv-wsl/bin/activate

mkdir -p "$(dirname "${RSS_TRACE_OUT}")"
: > "${RSS_TRACE_OUT}"

echo "$(date -Is) starting monitored sweep: process=${PROCESS} ceiling=${CEILING_GIB}GiB poll=${POLL_S}s rss_trace_out=${RSS_TRACE_OUT}" | tee "${LOG_FILE}"

python scripts/l22_evidence/sweep.py run --processes "${PROCESS}" --max-workers 1 --report-out "${REPORT_OUT}" \
    >> "${LOG_FILE}" 2>&1 &
SWEEP_PID=$!
echo "$(date -Is) sweep.py launched as PID ${SWEEP_PID}" | tee -a "${LOG_FILE}"

descendants() {
    # All PIDs in the process subtree rooted at $1, including itself.
    local root="$1"
    echo "${root}"
    ps -eo pid=,ppid= | awk -v root="${root}" '
        { children[$2] = children[$2] " " $1 }
        function collect(p,   c, kids, i) {
            kids = children[p]
            n = split(kids, arr, " ")
            for (i = 1; i <= n; i++) {
                c = arr[i]
                if (c != "") { print c; collect(c) }
            }
        }
        END { collect(root) }
    '
}

total_rss_kb() {
    local pids
    pids=$(descendants "${SWEEP_PID}")
    local sum=0
    for pid in ${pids}; do
        if [ -r "/proc/${pid}/status" ]; then
            local rss
            rss=$(awk '/^VmRSS:/ {print $2}' "/proc/${pid}/status" 2>/dev/null || echo 0)
            sum=$(( sum + ${rss:-0} ))
        fi
    done
    echo "${sum}"
}

STOPPED_FOR_CEILING=0
while kill -0 "${SWEEP_PID}" 2>/dev/null; do
    RSS_KB=$(total_rss_kb)
    RSS_GIB=$(awk -v kb="${RSS_KB}" 'BEGIN { printf "%.2f", kb/1024/1024 }')
    NOW_ISO="$(date -Is)"
    echo "${NOW_ISO} subtree_rss_kb=${RSS_KB} (${RSS_GIB} GiB)" >> "${LOG_FILE}"
    # Append one self-contained JSON object per sample (JSONL, not a single
    # JSON array) so a mid-run SIGKILL never leaves an unparseable file.
    printf '{"ts": "%s", "process": "%s", "rss_kb": %s, "rss_gib": %s}\n' \
        "${NOW_ISO}" "${PROCESS}" "${RSS_KB}" "${RSS_GIB}" >> "${RSS_TRACE_OUT}"
    if [ "${RSS_KB}" -gt "${CEILING_KB}" ]; then
        echo "$(date -Is) CEILING EXCEEDED (${RSS_GIB} GiB > ${CEILING_GIB} GiB) -- stopping subtree safely" | tee -a "${LOG_FILE}"
        for pid in $(descendants "${SWEEP_PID}"); do kill -TERM "${pid}" 2>/dev/null; done
        sleep 5
        for pid in $(descendants "${SWEEP_PID}"); do kill -KILL "${pid}" 2>/dev/null; done
        STOPPED_FOR_CEILING=1
        break
    fi
    sleep "${POLL_S}"
done

wait "${SWEEP_PID}" 2>/dev/null
SWEEP_EXIT=$?
echo "$(date -Is) sweep.py finished/stopped; exit=${SWEEP_EXIT} stopped_for_ceiling=${STOPPED_FOR_CEILING}" | tee -a "${LOG_FILE}"
exit "${SWEEP_EXIT}"
