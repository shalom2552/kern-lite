# Host unit tests. To add a test: define its <SCOPE>_SRC, add it to SRC and TRG,
# and give it a link rule. Objects are derived from sources via .cpp -> .o.

# ---------- paths -----------------------------------
CC = g++
CFLAGS = -Wall -std=c++17 -Wextra -pedantic

PYTHONPATH = ..
VENV = ../.venv
VPYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest

# ---------- tests -----------------------------------
# --- codec ---
CODEC_SRC = host/test_codec.cpp ../firmware/protocol/codec.cpp ../firmware/protocol/crc32.cpp
# --- cross ---
CROSS_SRC = host/test_cross_vectors.cpp ../firmware/protocol/codec.cpp ../firmware/protocol/crc32.cpp
# --- dsp ---
DSP_SRC   = host/test_dsp.cpp ../firmware/protocol/crc32.cpp

# --- storage ---
STORAGE_SRC = host/test_storage.cpp ../firmware/storage/circular_log.cpp \
              host/fatfs_shim/ff.cpp ../firmware/protocol/crc32.cpp
CFLAGS += -Ihost/stubs -Ihost/fatfs_shim

# --- day 5 member A: FSM + command guards ---
FSM_SRC = host/test_fsm.cpp ../firmware/recorder/state_machine.cpp \
          ../firmware/recorder/command_handler.cpp ../firmware/storage/circular_log.cpp \
          host/fatfs_shim/ff.cpp ../firmware/protocol/crc32.cpp

# --- example: new suite ---
# EXAMPLE_SRC = host/test_example.cpp ../firmware/<module>/<module>.cpp ../firmware/protocol/crc32.cpp

# ---------- targets ---------------------------------
SRC = $(CODEC_SRC) $(CROSS_SRC) $(DSP_SRC) $(STORAGE_SRC) $(FSM_SRC)
OBJ = $(sort $(SRC:.cpp=.o))
TRG = test_codec test_cross_vectors test_dsp test_storage test_fsm

# ---------- build -----------------------------------
all: $(TRG)

$(VENV):
	python3 -m venv $(VENV)
	$(VPYTHON) -m pip install -r ../requirements.txt

%.o: %.cpp
	$(CC) $(CFLAGS) -c -o $@ $<

test_codec: $(CODEC_SRC:.cpp=.o)
	$(CC) $(CFLAGS) -o $@ $^

test_cross_vectors: $(CROSS_SRC:.cpp=.o)
	$(CC) $(CFLAGS) -o $@ $^

test_dsp: $(DSP_SRC:.cpp=.o)
	$(CC) $(CFLAGS) -o $@ $^

test_storage: $(STORAGE_SRC:.cpp=.o)
	$(CC) $(CFLAGS) -o $@ $^

test_fsm: $(FSM_SRC:.cpp=.o)
	$(CC) $(CFLAGS) -o $@ $^

# example: new suite (also add EXAMPLE_SRC to SRC and test_example to TRG)
# test_example: $(EXAMPLE_SRC:.cpp=.o)
# 	$(CC) $(CFLAGS) -o $@ $^

# ---------- run -------------------------------------
run: all $(VENV)
	@for exe in $(TRG); do \
		./$$exe || exit 1; \
	done
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) gs/ -v

# ---------- clean -----------------------------------
clean:
	rm -f $(TRG) $(OBJ)
	rm -rf _ffroot_*

.PHONY: all run clean
