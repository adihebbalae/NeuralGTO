// Routes global operator new/delete through mimalloc. All the solver's hot-path
// vector allocations go through operator new, so this replaces the contended
// Windows heap without touching malloc/free callers.
#include "mimalloc/include/mimalloc-new-delete.h"
