#pragma once

/**
 * @brief Boot entry point for the kern-lite application.
 * 
 * Performs platform setup, mounts storage, registers task queues/semaphores,
 * and starts the FreeRTOS scheduler.
 */
extern "C" void kern_boot();
