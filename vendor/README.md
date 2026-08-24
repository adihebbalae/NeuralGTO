# vendor/ — optimized TexasSolver build

The production solver is a fork of [bupticybee/TexasSolver](https://github.com/bupticybee/TexasSolver)
(`console` branch — the Qt-free lineage the release `console_solver` binaries
come from), with performance work on the local branch **`neuralgto-opt`**.

`TexasSolver/` and `mimalloc/` are plain git clones and are **not** committed to
this repo (TexasSolver is AGPL-3; keep the fork out of the MIT-licensed tree).
Everything needed to reproduce them is here:

| File | Purpose |
|---|---|
| `texassolver-neuralgto-opt.patch` | Full diff of `neuralgto-opt` vs upstream `console` branch |
| `build_solver.sh` | Windows build (MSYS2 UCRT64 g++) |
| `build_solver_linux.sh` | Linux/Oracle Ampere ARM64 build |
| `mimalloc_newdelete.cpp` | Routes global `operator new/delete` through mimalloc |

## Reproduce from scratch

```bash
cd vendor
git clone https://github.com/bupticybee/TexasSolver
cd TexasSolver && git checkout console
git apply ../texassolver-neuralgto-opt.patch
cd ..
git clone --depth 1 --branch v2.1.7 https://github.com/microsoft/mimalloc
./build_solver_linux.sh build        # or build_solver.sh on Windows
```

## What the patch changes (and why it's ~2.3x faster)

1. **Strategy caching** — `DiscountedCfrTrainable::getcurrentStrategy()` returned
   a freshly allocated vector, recomputed from regrets, on *every* action-node
   visit (twice per iteration per node, plus once more inside `updateRegrets`).
   Now it's a lazily invalidated cached buffer returned by const reference.
2. **Lock-free river ranges** — `RiverRangeManager` took a global mutex on every
   showdown evaluation (the hottest leaf in the tree, hit from 8+ threads).
   All reachable river ranges are now precomputed in parallel before training,
   the cache is frozen, and lookups are lock-free. Ranges are stored as
   structure-of-arrays so the two-pointer showdown sweep streams sequentially.
3. **Raw-pointer recursion** — the CFR recursion copied `shared_ptr`s (atomic
   refcounts) and used `dynamic_pointer_cast` (RTTI) at every node visit. The
   tree owns all nodes for the solve's lifetime, so the recursion now uses raw
   pointers and a `getType()` switch with static casts.
4. **OpenMP tuning** — the chance-node `parallel for` now runs only at the
   split round (nested visits used to spawn a useless serialized team per
   visit) and uses `schedule(dynamic)` since per-card subtree cost varies.
5. **Copy elimination + vectorization** — per-card/per-action utility vector
   copies removed; regret/payoff/DCFR-update loops rewritten as contiguous,
   branchless passes over raw arrays; stack arrays replace 52-float heap
   vectors; `popcount` replaces a `long2board()` allocation per chance visit.
6. **Build flags** — `-O3 -march=native` (`-mcpu=native` on aarch64), LTO.
   Upstream's CMakeLists accidentally overwrites its own flags, so release
   binaries may not even be fully optimized.
7. **mimalloc** — global `operator new/delete` override; the recursion still
   allocates result vectors per node, and Windows' locked heap was measurable
   contention. Worth ~15% on top of everything else.
8. **Fixes** — `steady_clock` for progress timing (the old `system_clock` diff
   jumped by hours when NTP resynced mid-solve).

## Benchmark (sample flop spot, 8 threads, accuracy 0.5% pot)

| Build | Solve time | Per 10 iterations |
|---|---|---|
| Stock v0.2.0 release binary | 67.5 s | ~10.4 s |
| Same source, proper `-O3 -march=native` | ~59 s | ~7.4 s |
| `neuralgto-opt` + mimalloc | **29.8 s** | **~4.4 s** |
| ... with 16 threads | 22.3 s | — |

Convergence trajectories match per-iteration; final root strategy agrees with
the stock binary within 0.03% mean per-action frequency. Turn- and river-root
spots validated separately.

## Deployment

- **Local Windows:** `solver_bin/TexasSolver-opt-Windows/console_solver.exe`
  (already built; `.env` points at it).
- **Oracle backend:** rebuild on the box with `build_solver_linux.sh` and point
  the service's `SOLVER_BINARY_PATH` at the new binary. The resources folder is
  unchanged and can be shared with the stock install.
