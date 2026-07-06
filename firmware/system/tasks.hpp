#pragma once

/**
 * Creates and starts the four statically-allocated RTOS application tasks
 * (Sensor, Storage, Comms, System). Initializes the Orchestrator singleton.
 * Must be called once from kern_boot(). No heap allocation (NFR-02).
 */
void kern_create_tasks();
