#include "tasks.hpp"
#include "tasks_defs.hpp"
#include "orchestrator.hpp"
#include "FreeRTOS.h"
#include "task.h"

using O = kern::system::Orchestrator;

static StaticTask_t sensorTcb, storageTcb, commsTcb, systemTcb;
static StackType_t sensorStack[kern::tasks::kSensorStack];
static StackType_t storageStack[kern::tasks::kStorageStack];
static StackType_t commsStack[kern::tasks::kCommsStack];
static StackType_t systemStack[kern::tasks::kSystemStack];

static void sensorTask(void*)    
{ 
    // Dedicated wrapper keeps the FreeRTOS entry point tiny and explicit.
    O::instance().runSensorTask(); 
}

static void storageTask(void*)   
{ 
    // Storage runs as its own task so mounting and writes do not block sensors.
    O::instance().runStorageTask(); 
}

static void commsTask(void*)     
{ 
    // Communications stays separate so frame handling can evolve independently.
    O::instance().runCommsTask(); 
}

static void systemTask(void*)    
{ 
    // System work stays isolated so watchdog servicing is always periodic.
    O::instance().runSystemTask(); 
}

void kern_create_tasks()
{
    // Create all tasks with fixed stacks so the RTOS footprint stays explicit.
    O::instance().init();
    xTaskCreateStatic(sensorTask, "Sensor", kern::tasks::kSensorStack, nullptr,
                      kern::tasks::kSensorPrio, sensorStack, &sensorTcb);
    xTaskCreateStatic(storageTask, "Storage", kern::tasks::kStorageStack, nullptr,
                      kern::tasks::kStoragePrio, storageStack, &storageTcb);
    xTaskCreateStatic(commsTask, "Comms", kern::tasks::kCommsStack, nullptr,
                      kern::tasks::kCommsPrio, commsStack, &commsTcb);
    xTaskCreateStatic(systemTask, "System", kern::tasks::kSystemStack, nullptr,
                      kern::tasks::kSystemPrio, systemStack, &systemTcb);
}

extern "C" {
void vApplicationGetIdleTaskMemory(StaticTask_t** tcb, StackType_t** stack, uint32_t* size)
{
    // FreeRTOS asks for static idle-task storage when heap allocation is disabled.
    static StaticTask_t idleTcb;
    static StackType_t idleStack[configMINIMAL_STACK_SIZE];
    *tcb=&idleTcb; *stack=idleStack; *size=configMINIMAL_STACK_SIZE;
}

void vApplicationGetTimerTaskMemory(StaticTask_t** tcb, StackType_t** stack, uint32_t* size)
{
    // Same pattern for the timer service task.
    static StaticTask_t timerTcb;
    static StackType_t timerStack[configTIMER_TASK_STACK_DEPTH];
    *tcb=&timerTcb; *stack=timerStack; *size=configTIMER_TASK_STACK_DEPTH;
}

} // extern "C"
