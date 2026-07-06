# append the new target name (without .cpp) to the TRG variable
CC = g++
CFLAGS = -Wall -std=c++17 -Wextra -pedantic

PYTHONPATH = ..
VENV = ../.venv
VPYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest

COMMON = ../firmware/protocol/codec.cpp ../firmware/protocol/crc32.cpp
TRG = test_codec test_cross_vectors test_dsp

all: $(TRG)

$(VENV):
	python3 -m venv $(VENV)
	$(VPYTHON) -m pip install -r requirements.txt

$(TRG): %: host/%.cpp $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^

run: all $(VENV)
	@for exe in $(TRG); do \
		./$$exe || exit 1; \
	done
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) gs/ -v

clean:
	rm -f $(TRG) *.o host/*.o ../firmware/protocol/*.o

.PHONY: all run clean