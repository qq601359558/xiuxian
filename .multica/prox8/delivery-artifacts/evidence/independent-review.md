No blocking finding. The prior P2 is resolved.

- `server/app.py:20` builds an immutable allow-list from the static catalog’s normalized commands/aliases. Exact membership checks replace free text and unknown slash commands with fixed markers (`server/app.py:329`).
- `server/app.py:337` logs fixed `ACTION_REJECTED`, retaining the original HTTP 200 rejection body. Exception diagnostics contain only type and frame metadata—not exception messages, source text, input, or tokens (`server/app.py:339`).
- Dispatch still receives the original command (`server/app.py:335`). HTTP tests cover all three failure-input forms, recovery, rejection privacy, and 400/200 compatibility (`tests/test_world_action_regressions.py:296`, `tests/test_world_action_regressions.py:343`, `tests/test_world_action_regressions.py:355`).

This read-only review is not QA acceptance; browser and independent QA acceptance remain pending.

Decision: PASS