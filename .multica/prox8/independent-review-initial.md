- **P2 — Raw player input can leak into exception logs** — `server/app.py:332`. `command_name` is the unrestricted first whitespace-delimited token. Since `World.handle` supports unprefixed text, a command such as `私密输入` is logged verbatim in `CMD` and `ERROR` when processing raises, violating the diagnostic-redaction contract. Log recognized command verbs only, using a fixed marker otherwise. Extend the HTTP privacy regression to cover unprefixed text and unknown commands; its current `/做 私密输入` case misses this.

No additional in-scope blocking findings identified. This review runs no tests and does not constitute QA acceptance; browser/QA verification remains outstanding.

Decision: CHANGES_REQUESTED — exception logging does not fully satisfy the accepted privacy contract.