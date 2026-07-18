# KERN-LITE — Design Note

## 1. `LogMeta` byte layout

`#pragma pack(push, 1)`, 36 bytes total, CRC computed over bytes 0–31


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

## 3. Robustness scenario: power-loss mid-write recovery

This is the primary robustness
evidence for the "DATA SURVIVABILITY" theme: every stored
record is independently checksummed, the ring only overwrites the
oldest retained data, metadata is persisted periodically, and the
recorder reconstructs its write head after an unexpected reset.

### Procedure (run on hardware)

1. `CMD_START` from Idle.
2. Let it run ~40 s (≥3 metadata flush cycles at `META_FLUSH_EVERY_N = 16`,
   10 Hz sample rate).
3. Pull power abruptly (no `CMD_STOP` first — this must be an *unclean*
   cut, not a graceful shutdown).
4. Restore power, let the board boot and re-mount.
5. Reconnect the GS and issue `CMD_STATUS`.
6. Issue `CMD_REPLAY 20`.

### Expected

- `StatusPoller` on the GS flags `REBOOT_DETECTED` (total_records drops
  between polls).
- `total_records` in the post-reset STATUS is close to, but may trail,
  the pre-reset value by up to `META_FLUSH_EVERY_N` (16) records — the
  gap the forward-scan recovery is designed to close.
- All 20 replayed records pass both frame CRC and record CRC.
- Starting a new `CMD_START` afterward writes at the correct recovered
  position — no overwrite of the still-valid pre-reset records, and no
  gap larger than `META_FLUSH_EVERY_N`.

