# KERN-LITE — Design Note

## 1. `LogMeta` byte layout

`#pragma pack(push, 1)`, 36 bytes total, CRC computed over bytes 0–31
(spec §10.3 is ground truth here — not the handbook's record-CRC range,
which applies to the unrelated 32-byte `SensorRecord`).

| Offset | Size | Field              | Encoding                          |
|-------:|-----:|--------------------|------------------------------------|
| 0      | 4    | `magic`            | u32 LE, `0x4C4F4700` ("LOG\0")     |
| 4      | 4    | `version`          | u32 LE, `1`                        |
| 8      | 1    | `file_count`       | u8, `LOG_FILE_COUNT` (4)           |
| 9      | 2    | `records_per_file` | u16 LE, `RECORDS_PER_FILE` (256)   |
| 11     | 1    | `current_file`     | u8, index of active log file       |
| 12     | 2    | `write_index`      | u16 LE, next slot in current file  |
| 14     | 4    | `wrap_count`       | u32 LE, completed full-ring wraps  |
| 18     | 4    | `total_records`    | u32 LE, cumulative writes since erase |
| 22     | 10   | `reserved`         | zeroed on write                    |
| 32     | 4    | `crc32`            | u32 LE, over bytes 0–31            |

Total capacity: `LOG_FILE_COUNT × RECORDS_PER_FILE` = 1024 records
(32 KB retained). At the 10 Hz sample rate this is ~102.4 s per wrap.

## 2. Recovery algorithm

On mount, `META.BIN` is read and validated (magic, version, CRC). If it
passes, it is treated as a *checkpoint, not the final head* — the write
head can trail the true position by up to `META_FLUSH_EVERY_N` (16)
records, since metadata is only persisted every 16 writes and on STOP.
The mounter therefore scans forward from the checkpoint, one slot at a
time, accepting each slot whose record CRC is valid and whose
`(timestamp, ms, seq)` ordering is strictly newer than the previous
accepted record; the scan stops at the first invalid or non-newer slot,
and that position becomes the recovered write head. If metadata is
missing or fails validation, `recoverPosition()` instead scans every
slot in the ring, validates each record's CRC, and — because a
completely wrapped ring has no invalid/valid boundary — picks the
*newest* valid record by `(timestamp, ms, seq)` rather than assuming a
contiguous prefix; the slot after it becomes the head. Neither path
ever rewrites or erases a slot it doesn't overwrite in the normal course
of new writes, so a botched recovery cannot destroy data that was
otherwise intact.

## 3. Robustness scenario: boot-time storage availability

**Scope note:** this scenario was found and traced through code review
during the A6.1 audit (no hardware pass yet) — the team should still run
the physical power-pull test (Day 7, T5) to confirm hardware behavior
matches this trace.

**Expected:** per spec FR-FW-01, on cold boot the firmware mounts or
recovers storage *before* entering Idle, so `CMD_STATUS` reports
`sd_mounted=1` and `CMD_REPLAY` works immediately after boot — including
right after an unexpected reset, without requiring a START first.

**Observed (before fix):** `Orchestrator::init()` never called
`m_box.mount()`. Mounting only happened lazily inside `ensureMounted()`,
guarded by `m_sm.isLogging()` — so it only ran once `CMD_START` had
already been sent. A GS operator connecting right after a power-loss
event and issuing `CMD_REPLAY` to check for surviving data would get
`NACK StorageError` even though the SD card held valid, recoverable
records, because `isMounted()` was still `false`.

**Fix applied:** `Orchestrator::init()` now calls `m_box.mount()`
directly, so recovery (checkpoint-plus-forward-scan or full scan, per
§2 above) runs at boot as required. `ensureMounted()` in the Storage
task is unchanged and still owns retry/escalation to `Fault` if the
card is physically absent or fails to mount (FR-FW-14).

**Result:** with the fix, `CMD_STATUS`/`CMD_REPLAY` reflect the
recovered ring state immediately after boot. Team should now run T5
(power-pull mid-write, spec §14.2) on hardware to confirm the same
holds for a genuinely interrupted write, not just a clean-then-recover
boot.

## Other findings from this audit (see firmware diffs)

- **Fault-transition STATUS**: spec §12.2 requires an immediate STATUS
  frame on `Recording→Fault` (3rd consecutive write failure) and on
  `Fault→Recording` (successful remount). Previously only the 5 s
  heartbeat covered these; fixed by sending STATUS at both transition
  points.
- **Degraded-recording LED**: spec §6.3 distinguishes solid green
  (nominal) from blinking green (`Recording` with `fault_bits` set).
  Previously the LED was always solid while recording; fixed by
  tracking the latest record's `fault_bits` and blinking accordingly.
- **`WriteFailurePolicy` (now reviewed)**: counting logic is correct —
  traced as fail 1 → tolerate, fail 2 → tolerate, fail 3 → trigger,
  matching FR-FW-14 exactly. However `orchestrator.cpp` carried its own
  local `MAX_WRITE_FAILS = 3` (for the Fault-state remount-retry limit)
  separate from `WriteFailurePolicy`'s own default `maxFails = 3` — two
  constants that happened to agree but could silently diverge on a
  future edit. Consolidated into a single `kern::config::kMaxWriteFails`
  (spec Appendix A: "Maximum consecutive write failures = 3"), used by
  both the policy's constructor and the reboot-retry check.
