CC = g++
CFLAGS = -Wall -std=c++17 -Wextra -pedantic
PYTHON = python
PYTHONPATH = ..

COMMON = ../firmware/protocol/codec.cpp ../firmware/protocol/crc32.cpp

all: test_codec test_cross_vectors

test_codec: host/test_codec.cpp $(COMMON)
	$(CC) $(CFLAGS) -o test_codec host/test_codec.cpp $(COMMON)

test_cross_vectors: host/test_cross_vectors.cpp $(COMMON)
	$(CC) $(CFLAGS) -o test_cross_vectors host/test_cross_vectors.cpp $(COMMON)

run: all
	./test_codec
	./test_cross_vectors
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest gs/test_codec.py -v
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest gs/test_cross_vectors.py -v

clean:
	rm -f test_codec test_cross_vectors *.o host/*.o ../firmware/protocol/*.o

.PHONY: all run clean