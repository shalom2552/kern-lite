#include "init.hpp"
#include "tasks.hpp"

extern "C" void kern_boot() {
    // The C entry point stays tiny: once the runtime is ready, hand control to
    // the task bootstrap layer and let FreeRTOS take over.
    kern_create_tasks();
}
