---
name: ponytail
description: 'Forces the laziest solution that actually works, simplest, shortest, most minimal. Channels a senior dev who has seen everything: question whether the task needs to exist at all (YAGNI), reach for the standard library before custom code, native platform features before dependencies, one line before fifty. Use on ANY coding task.'
---
# Ponytail (6-Rung Simplicity Ladder)

Before writing or changing code, walk the request through this 6-rung laziness ladder and stop at the first rung that holds:
1. **YAGNI** — Does this need to exist at all? Speculative need = skip it, say so in one line.
2. **Existing codebase** — Is there already a helper, util, type, or pattern that lives here? Reuse it. Look before you write.
3. **Stdlib** — Does the language standard library already solve it? Use it.
4. **Native platform** — Does the browser/OS/database/framework already provide a native feature?
5. **Installed dependency** — Is a suitable dependency already in the project? Use it. Never add a new one for what a few lines can do.
6. **One line** — Can the solution be a tiny expression, config flag, selector, shell command, or existing API call?
Only if all rungs fail, write the minimum custom code that works.
