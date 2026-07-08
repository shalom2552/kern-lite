#include "init.hpp"
#include "tasks.hpp"

extern "C" void kern_boot() {
    // Boot hands off to the task bootstrap layer.
    kern_create_tasks();
}
