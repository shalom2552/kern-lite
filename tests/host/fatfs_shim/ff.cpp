/*
Host FatFs shim implementation. See ff.h.

file: tests/host/fatfs_shim/ff.cpp
author: shalom2552
date: 2026-07-07
*/

#include "ff.h"

#include <sys/stat.h>
#include <cstring>
#include <cstdio>

static char g_root[512] = ".";

// Map a FatFs path ("0:NAME" or "NAME") to a host path under the test root.
const char* ff_test_path(const char* name)
{
    static char buf[640];
    const char* base = name;
    if (base[0] != '\0' && base[1] == ':') {
        base += 2; // skip volume prefix like "0:"
    }
    std::snprintf(buf, sizeof(buf), "%s/%s", g_root, base);
    return buf;
}

void ff_test_set_root(const char* dir)
{
    std::snprintf(g_root, sizeof(g_root), "%s", dir);
    mkdir(g_root, 0777);
}

FRESULT f_mount(FATFS* fs, const char*, BYTE)
{
    if (fs) {
        fs->mounted = 1;
    }
    return FR_OK;
}

FRESULT f_open(FIL* fp, const char* path, BYTE mode)
{
    if (!fp || !path) {
        return FR_INVALID_PARAMETER;
    }
    const char* host = ff_test_path(path);
    FILE* h = nullptr;

    if (mode & FA_CREATE_ALWAYS) {
        h = std::fopen(host, "w+b"); // truncate + create
    } else if ((mode & FA_OPEN_ALWAYS) || (mode & FA_WRITE)) {
        h = std::fopen(host, "r+b"); // open existing R/W, keep contents
        if (!h) {
            h = std::fopen(host, "w+b"); // create if absent
        }
    } else {
        h = std::fopen(host, "rb"); // read-only
    }
    if (!h) {
        return FR_NO_FILE;
    }

    std::fseek(h, 0, SEEK_END);
    long sz = std::ftell(h);
    std::fseek(h, 0, SEEK_SET);

    fp->host = h;
    fp->fptr = 0;
    fp->obj.objsize = sz < 0 ? 0 : static_cast<FSIZE_t>(sz);
    return FR_OK;
}

FRESULT f_close(FIL* fp)
{
    if (fp && fp->host) {
        std::fclose(fp->host);
        fp->host = nullptr;
    }
    return FR_OK;
}

FRESULT f_read(FIL* fp, void* buff, UINT btr, UINT* br)
{
    if (!fp || !fp->host) {
        return FR_INVALID_PARAMETER;
    }
    size_t n = std::fread(buff, 1, btr, fp->host);
    fp->fptr += n;
    if (br) {
        *br = static_cast<UINT>(n);
    }
    return FR_OK;
}

FRESULT f_write(FIL* fp, const void* buff, UINT btw, UINT* bw)
{
    if (!fp || !fp->host) {
        return FR_INVALID_PARAMETER;
    }
    size_t n = std::fwrite(buff, 1, btw, fp->host);
    fp->fptr += n;
    if (fp->fptr > fp->obj.objsize) {
        fp->obj.objsize = fp->fptr;
    }
    if (bw) {
        *bw = static_cast<UINT>(n);
    }
    return FR_OK;
}

FRESULT f_lseek(FIL* fp, FSIZE_t ofs)
{
    if (!fp || !fp->host) {
        return FR_INVALID_PARAMETER;
    }
    if (std::fseek(fp->host, static_cast<long>(ofs), SEEK_SET) != 0) {
        return FR_DISK_ERR;
    }
    fp->fptr = ofs;
    return FR_OK;
}

FRESULT f_sync(FIL* fp)
{
    if (fp && fp->host) {
        std::fflush(fp->host);
    }
    return FR_OK;
}

FRESULT f_unlink(const char* path)
{
    if (!path) {
        return FR_INVALID_PARAMETER;
    }
    if (std::remove(ff_test_path(path)) != 0) {
        return FR_NO_FILE;
    }
    return FR_OK;
}
