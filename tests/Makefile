CC = g++
CFLAGS = -Wall -std=c++17 -Wextra -pedantic -Werror

SRC = host/test_codec.cpp ../firmware/protocol/codec.cpp ../firmware/protocol/crc32.cpp 
OBJ = $(SRC:.cpp=.o)
TARGET = test

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $(TARGET) $(OBJ)

%.o: %.cpp
	$(CC) $(CFLAGS) -c $< -o $@

.PHONY: clean
clean:
	rm -f $(TARGET) $(OBJ)