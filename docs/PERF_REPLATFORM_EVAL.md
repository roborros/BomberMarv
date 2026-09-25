# Replatform Evaluation

## Scope

- Compare current Canvas2D pipeline against a WebGL baseline.
- Identify practical migration paths if gameplay targets require stable `>=30 FPS` with low present delay.

## How to run benchmark

- Start the stack as usual.
- Open web client with `?bench=1`, for example `http://127.0.0.1:5173/?bench=1`.
- Results are printed in browser console via `console.table`.

Benchmark implementation:

- `web_client/src/perf_benchmark.ts`
- Triggered from `web_client/src/main.ts`

## Interpreting benchmark output

- `fps`: achieved frame rate during stress draw loop
- `avgFrameMs`: average frame cost
- `p95FrameMs`: tail latency of frame cost (jank indicator)

Guidance:

- If Canvas2D `p95FrameMs > 20ms` under typical board/entity complexity, it will struggle to hold 50-60 FPS.
- If WebGL has lower `p95FrameMs` by a meaningful margin, migration buys headroom.

## Recommended migration ladder

1. Keep current architecture and optimize Canvas2D path first.
   - Already implemented: static board layer caching in `renderer.ts`.
2. If client still fails to hold target FPS, migrate renderer to WebGL.
   - Candidate stacks: PixiJS (low-level sprite control), Phaser (higher-level scene framework).
3. If transport/decode dominates after renderer migration, move decode + interpolation to Web Worker and move to binary snapshot/delta transport.

## Radical options (if long-term roadmap allows)

- Headless authoritative simulation service with host UI as client.
- Shared deterministic sim core (Rust/WASM or TypeScript) used by host and web paths.
- Full web-native authoritative backend with Python host retained only for legacy mode.

## Decision gate

Use these criteria:

- Gameplay feel: no constant visual behind-feel during normal movement.
- Client FPS: sustained `>=30` in 6-player scenario.
- Present delay p95: trend down after buffered rendering and delta transport.
