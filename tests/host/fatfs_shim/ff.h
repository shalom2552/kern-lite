/*
Minimal host FatFs shim for CircularLog unit tests. Backs each FatFs file with a
regular stdio FILE* under a test root directory. Only the subset of the FatFs API
used by circular_log.cpp is implemented.

file: tests/host/fatfs_shim/ff.h
author: shalom2552
date: 2026-07-07
*/

#pragma once

#include <cstdint>
#include <cstdio>

typedef unsigned char BYTE;
typedef unsigned int UINT;
typedef uint32_t DWORD;
typedef uint64_t FSIZE_t;

typedef enum {
    FR_OK = 0,
    FR_DISK_ERR,
    FR_NO_FILE,
    FR_INVALID_PARAMETER
} FRESULT;

/* f_open mode flags (same bit values as real FatFs). */
#define FA_READ          0x01
#define FA_WRITE         0x02
#define FA_OPEN_EXISTING 0x00
#define FA_CREATE_NEW    0x04
#define FA_CREATE_ALWAYS 0x08
#define FA_OPEN_ALWAYS   0x10

struct FFOBJID {
    FSIZE_t objsize;
};

typedef struct {
    int mounted;
} FATFS;

typedef struct {
    FFOBJID obj;   // obj.objsize = current file size (read by f_size)
    FSIZE_t fptr;  // current read/write offset
    FILE* host;    // backing stdio handle
} FIL;

#define f_size(fp) ((fp)->obj.objsize)
#define f_tell(fp) ((fp)->fptr)

FRESULT f_mount(FATFS* fs, const char* path, BYTE opt);
FRESULT f_open(FIL* fp, const char* path, BYTE mode);
FRESULT f_close(FIL* fp);
FRESULT f_read(FIL* fp, void* buff, UINT btr, UINT* br);
FRESULT f_write(FIL* fp, const void* buff, UINT btw, UINT* bw);
FRESULT f_lseek(FIL* fp, FSIZE_t ofs);
FRESULT f_sync(FIL* fp);
FRESULT f_unlink(const char* path);

/* Test helpers (not part of FatFs). */
void ff_test_set_root(const char* dir); // set + create the directory backing "0:"
const char* ff_test_path(const char* name); // map "0:NAME" (or "NAME") to a host path
