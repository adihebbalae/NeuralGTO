#!/bin/bash
# Build the optimized TexasSolver console_solver on Linux (incl. Oracle Ampere
# ARM64). Run from the vendor/ directory with TexasSolver/ checked out on the
# neuralgto-opt branch (or apply texassolver-neuralgto-opt.patch to the
# upstream console branch).
#
#   ./build_solver_linux.sh <build_dir>
#
# Requires: g++ >= 9 with OpenMP. mimalloc is optional but worth ~15%:
#   git clone --depth 1 --branch v2.1.7 https://github.com/microsoft/mimalloc
set -e
SRC="$(cd "$(dirname "$0")/TexasSolver" && pwd)"
VENDOR="$(cd "$(dirname "$0")" && pwd)"
BUILD="${1:?usage: build_solver_linux.sh <build_dir>}"
mkdir -p "$BUILD/obj"

# -mcpu=native on aarch64 (where -march=native is not supported), -march=native elsewhere
if [ "$(uname -m)" = "aarch64" ]; then ARCHFLAG="-mcpu=native"; else ARCHFLAG="-march=native"; fi

CXXFLAGS="-std=c++17 -O3 $ARCHFLAG -funroll-loops -fopenmp -flto=auto -DNDEBUG -DFMT_HEADER_ONLY \
  -I$SRC/include -I$SRC -I$SRC/ext/fmt/include"

EXTRA_OBJS=""
if [ -d "$VENDOR/mimalloc" ]; then
  gcc -std=gnu11 -O3 -DNDEBUG -I"$VENDOR/mimalloc/include" -c "$VENDOR/mimalloc/src/static.c" -o "$BUILD/obj/mimalloc_static.o"
  g++ -std=c++17 -O3 -DNDEBUG -I"$VENDOR/mimalloc/include" -c "$VENDOR/mimalloc_newdelete.cpp" -o "$BUILD/obj/mimalloc_newdelete.o"
  EXTRA_OBJS="$BUILD/obj/mimalloc_newdelete.o $BUILD/obj/mimalloc_static.o"
fi

SOURCES=$(ls "$SRC"/src/{Card,Deck,GameTree,library,console}.cpp \
  "$SRC"/src/compairer/*.cpp "$SRC"/src/nodes/*.cpp "$SRC"/src/ranges/*.cpp \
  "$SRC"/src/tools/*.cpp "$SRC"/src/trainable/*.cpp \
  "$SRC"/src/solver/{BestResponse,PCfrSolver,Solver}.cpp \
  "$SRC"/src/runtime/*.cpp)

OBJS=()
for f in $SOURCES; do
  obj="$BUILD/obj/$(basename "${f%.cpp}").o"
  OBJS+=("$obj")
  if [ ! -f "$obj" ] || [ "$f" -nt "$obj" ]; then
    g++ $CXXFLAGS -c "$f" -o "$obj" &
    while [ "$(jobs -rp | wc -l)" -ge "$(nproc)" ]; do wait -n; done
  fi
done
wait

g++ $CXXFLAGS "${OBJS[@]}" $EXTRA_OBJS -lpthread -o "$BUILD/console_solver"
echo "BUILT: $BUILD/console_solver"
