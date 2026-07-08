#include "state_machine.hpp"

namespace kern::recorder { bool StateMachine::process(Event) {
	// Keep the interface in place even though the real event transitions are
	// still pending, so the recorder subsystem can compile and evolve in stages.
	return false;
} }
