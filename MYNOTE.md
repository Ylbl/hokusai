# MyNote integration branch

Upstream: <https://github.com/reearth/hokusai>  
Fork: <https://github.com/Ylbl/hokusai>

## Keep the fork thin

- Keep the upstream simulation loop unique. Do not copy `stroke_to`, shadow the parser/settings list, or maintain a parallel state machine.
- Put integration code in `crates/hokusai-core/src/mynote_ext.rs`; upstream files contain only the required entry/state/context/grid insertion points and separately identifiable MyPaint correctness fixes.
- Preserve the upstream public `Brush::stroke_to` arguments. A host provides view/barrel context through `TiledSurface::stroke_input_context`; explicit catch-up retains the last accepted context.
- The state extension is grouped in `BrushState::mynote`. World-coordinate policy, resource lifetime, document logic and GPU execution remain outside Hokusai.
- Query required grid axes once when compiling an immutable host brush. Do not add a mutation-sensitive cache to upstream `Brush`.
- `packed_dab` exhaustively covers the current Dab fields. An upstream field addition must stop compilation rather than be silently dropped by the GPU transport.
- Seed/state observation is development-only under `reference-probe`; keep the original unseeded reset API usable by upstream consumers.

## Follow upstream main

`MyNote upstream sync` checks upstream every 15 minutes, and also supports manual dispatch. It creates a candidate without changing main, explicitly dispatches the complete `CI` workflow, then publishes only the exact commit identified by that workflow's success event. CI retains upstream jobs and adds a Linux cargo-xwin build whose actual MSVC test executables run on a hosted Windows runner. No polling coordinator, force push or conflict preference is used.

The candidate ref identifies both the upstream commit and the fork's starting main commit. A conflict, changed CI identity, missing native gate, failed check, stale base or changed candidate stops publication. Failed candidates remain available for diagnosis; the same candidate is not automatically resubmitted every 15 minutes. `force_checks` explicitly rechecks it.

The integration with the existing upstream CI file is deliberately small: enable `workflow_dispatch` and call the separate MyNote native workflow. Do not replace upstream CI with a frozen duplicate of its jobs.

GitHub scheduling is periodic, not an upstream webhook or an uptime guarantee. Provider delays and GitHub's inactivity-related schedule disablement still apply; manual dispatch/reenabling remains available.

## What updates inherit

Additive parsing, input mappings and simulation improvements within the current host protocol flow through the original upstream code. This is not a promise that arbitrary API breaks, new Surface requirements or new pixel algorithms automatically work in MyNote WGSL. Those require compatibility validation and possibly a small adapter/shader change. Never merge with ours/force to conceal conflicts, discard new fields, or claim a held-back update is already integrated.

The native fork gate validates this library, not the MyNote application window or GPU fidelity. MyNote must separately update its pinned dependency and run its application/GPU replay checks before shipping a new fork revision. Keep replay kernel semantic identity distinct from source commit/version: compatible source-only updates must not gratuitously invalidate old notebooks; changed replay semantics require an explicit compatibility decision.
