# KERN-LITE — Phase 7 Validation Results

Integration, validation, and demo evidence for the final quality gate.
Every scenario from the fault-injection battery is exercised and its result recorded here.

## Test Environment

| Item | Value |
|---|---|
| Date | 2026/07/15 |
| Board | NUCLEO-L476RG |
| SD card | Sandisk microSD 64GB |
| Toolchain / IDE version | CubeIDe |
| Python version | Python 3.14.6 |


## Fault-Injection Battery — Summary


| ID | Scenario | Result (Pass/Fail) |
|---|---|---|
| T1 | Full wraparound demo | PASS |
| T2 | REPLAY across file boundary | PASS |
| T3 | REPLAY overflow | PASS |
| T4 | REPLAY with N = 0 | PASS |
| T5 | Power-loss mid-write recovery | PASS |
| T6 | Corrupt frame on the link | PASS |
| T7 | Corrupt stored record | PASS |
| T8 | ERASE wrong magic | PASS |
| T9 | Command gating | PASS |
| T10 | Link drop / auto-reconnect | PASS |
| T11 | DHT11 fault recovery | PASS |
| T12 | SD fault and recovery (if injectable) | PASS |


## Full Test Suite — Final Run

All tests must pass after any changes made during this phase.

```sh
# Host C++ tests
cd tests/host && make && ./test_codec && ./test_dsp && ./test_storage && ./test_fsm
# Python tests
cd tests/gs && pytest -v
```

| Suite | Result |
|---|---|
| test_codec (host) | PASS |
| test_dsp (host) | PASS |
| test_storage (host) | PASS |
| test_fsm (host) | PASS |
| pytest (tests/gs) | PASS |


## Demo Artifacts Checklist

Saved under `docs/demo/`:

- [ ] Session CSV export (headers, all five channels, scaled values)
- [ ] Alert log text export
- [ ] State timeline text export
- [ ] Raw frame log export
- [ ] `screenshot_wraparound.png` (storage panel showing file advance, chart scrolling, stats populated)
- [ ] `docs/README.md` complete (build/flash, GS run steps, wiring/pinout, CRC known-answer, configured constants, test commands)
- [ ] `docs/design_note.md` finalized (LogMeta byte layout, recovery algorithm, T5 robustness scenario)

## End-of-Phase Review (Final Demo)

- [ ] T1 demo live: start fresh (erase), record 110 s, show `wrap_count` increment in real time.
- [ ] T2: issue REPLAY 300; 300 records arrive, all CRC-green, spanning two files.
- [ ] T5 evidence: show design note + T5 procedure and result; pull power mid-write live and show recovery.
- [ ] T6 + T7: inject one frame-CRC error (counter increments); show storage-corruption warning from T7.
- [ ] T9: run command-gating checks from Idle and Recording states.
- [ ] Full test suite live: host tests and `pytest -v` all green.
- [ ] CSV opened in a spreadsheet; `lm35_celsius` column shows plausible values.
- [ ] Screenshot + design note present in `docs/`.

**Gate:** T1–T12 battery passes; full test suite and artifacts complete.
