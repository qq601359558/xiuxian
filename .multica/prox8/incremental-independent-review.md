No blocking finding in the scoped F2/F3 follow-up.

- **F2:** Status is generated after combat saves and bounty settlement/save, reflecting the settled balance (`server/world.py:3487`).
- **F3:** Alive/idle guards remain first (`server/world.py:1109`); target-node treasure routing precedes the unchanged ordinary creation guard (`server/world.py:1121`, `server/world.py:1127`).
- **Non-injection:** AI output supplies judgement/narrative only; success and fail-forward rewards remain engine-defined, ignoring forged rewards and stone deltas (`core/treasure_system.py:732`, `core/treasure_system.py:758`, `core/treasure_system.py:779`).
- **Tests:** Temporary storage isolates persistence. Probes retain real World routing and TreasureEngine rewards, comparing full non-UID item payloads and numeric deltas across ordinary/malicious narration in both outcomes (`tests/test_world_action_regressions.py:168`). Additional assertions expose no-map/off-target guard bypasses and missing/stale fight status (`tests/test_world_action_regressions.py:89`, `tests/test_world_action_regressions.py:315`).

Read-only review; no tests executed. This is not QA acceptance: F2 browser topbar evidence and independent incremental QA remain pending.

Decision: PASS