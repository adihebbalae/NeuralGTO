#!/bin/bash
# Build TexasSolver console_solver (console branch) with MSYS2 UCRT64 g++.
# Usage: build_solver.sh <build_dir> [extra CXXFLAGS...]
set -e
SRC="C:/Users/boomb/Documents/_Projects/neus_nlhe/vendor/TexasSolver"
GXX="C:/msys64/ucrt64/bin/g++.exe"
BUILD="${1:?usage: build_solver.sh <build_dir> [flags...]}"
shift || true
mkdir -p "$BUILD/obj"

CXXFLAGS="-std=c++17 -O3 -march=native -funroll-loops -fopenmp -DNDEBUG -DFMT_HEADER_ONLY \
  -DWIN32_LEAN_AND_MEAN -DNOMINMAX \
  -I$SRC/include -I$SRC -I$SRC/ext/fmt/include $*"

SOURCES=$(ls "$SRC"/src/{Card,Deck,GameTree,library,console}.cpp \
  "$SRC"/src/compairer/*.cpp "$SRC"/src/nodes/*.cpp "$SRC"/src/ranges/*.cpp \
  "$SRC"/src/tools/*.cpp "$SRC"/src/trainable/*.cpp \
  "$SRC"/src/solver/{BestResponse,PCfrSolver,Solver}.cpp \
  "$SRC"/src/runtime/*.cpp)

OBJS=()
PIDS=()
for f in $SOURCES; do
  obj="$BUILD/obj/$(basename "${f%.cpp}").o"
  OBJS+=("$obj")
  if [ ! -f "$obj" ] || [ "$f" -nt "$obj" ]; then
    "$GXX" $CXXFLAGS -c "$f" -o "$obj" &
    PIDS+=($!)
    # cap parallel compiles at 12
    while [ "$(jobs -rp | wc -l)" -ge 12 ]; do wait -n; done
  fi
done
FAIL=0
for p in "${PIDS[@]}"; do wait "$p" || FAIL=1; done
[ "$FAIL" -eq 0 ] || { echo "COMPILE FAILED"; exit 1; }

# EXTRA_OBJS: optional space-separated .o files linked in (e.g. mimalloc)
"$GXX" $CXXFLAGS "${OBJS[@]}" $EXTRA_OBJS -static -o "$BUILD/console_solver.exe"
echo "BUILT: $BUILD/console_solver.exe"
