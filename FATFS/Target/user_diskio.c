/* USER CODE BEGIN Header */
/**
 ******************************************************************************
  * @file    user_diskio.c
  * @brief   This file includes a diskio driver skeleton to be completed by the user.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
 /* USER CODE END Header */

#ifdef USE_OBSOLETE_USER_CODE_SECTION_0
/*
 * Warning: the user section 0 is no more in use (starting from CubeMx version 4.16.0)
 * To be suppressed in the future.
 * Kept to ensure backward compatibility with previous CubeMx versions when
 * migrating projects.
 * User code previously added there should be copied in the new user sections before
 * the section contents can be deleted.
 */
/* USER CODE BEGIN 0 */
/* USER CODE END 0 */
#endif

/* USER CODE BEGIN DECL */

/* Includes ------------------------------------------------------------------*/
#include <string.h>
#include "ff_gen_drv.h"
#include "main.h"
#include "spi.h"

/* Private typedef -----------------------------------------------------------*/
/* Private define ------------------------------------------------------------*/
#define SD_DUMMY_BYTE          0xFFu
#define SD_TOKEN_START_BLOCK   0xFEu
#define SD_TOKEN_MULTI_WRITE   0xFCu
#define SD_TOKEN_STOP_TRAN     0xFDu
#define SD_DATA_ACCEPTED       0x05u

#define SD_CMD0                0u
#define SD_CMD1                1u
#define SD_CMD8                8u
#define SD_CMD9                9u
#define SD_CMD12               12u
#define SD_CMD16               16u
#define SD_CMD17               17u
#define SD_CMD18               18u
#define SD_CMD24               24u
#define SD_CMD25               25u
#define SD_CMD55               55u
#define SD_CMD58               58u
#define SD_ACMD41              41u

#define CT_MMC                 0x01u
#define CT_SD1                 0x02u
#define CT_SD2                 0x04u
#define CT_BLOCK               0x08u

#define SD_SPI_TIMEOUT_MS      500u

/* Private variables ---------------------------------------------------------*/
/* Disk status */
static volatile DSTATUS Stat = STA_NOINIT;
static BYTE CardType = 0;

static void sd_select(void)
{
  HAL_GPIO_WritePin(SD_CS_GPIO_Port, SD_CS_Pin, GPIO_PIN_RESET);
}

static void sd_deselect(void)
{
  HAL_GPIO_WritePin(SD_CS_GPIO_Port, SD_CS_Pin, GPIO_PIN_SET);
}

static BYTE sd_spi_txrx(BYTE data)
{
  BYTE rx = SD_DUMMY_BYTE;
  (void)HAL_SPI_TransmitReceive(&hspi1, &data, &rx, 1, SD_SPI_TIMEOUT_MS);
  return rx;
}

static void sd_spi_clock(void)
{
  (void)sd_spi_txrx(SD_DUMMY_BYTE);
}

static int sd_wait_ready(UINT timeout_ms)
{
  uint32_t start = HAL_GetTick();
  BYTE resp;

  do {
    resp = sd_spi_txrx(SD_DUMMY_BYTE);
    if (resp == SD_DUMMY_BYTE) {
      return 1;
    }
  } while ((HAL_GetTick() - start) < timeout_ms);

  return 0;
}

static void sd_power_on_clocks(void)
{
  sd_deselect();
  for (uint8_t i = 0; i < 10; ++i) {
    sd_spi_clock();
  }
}

static BYTE sd_send_cmd(BYTE cmd, DWORD arg)
{
  BYTE crc = 0x01;
  BYTE resp;

  if (cmd & 0x80u) {
    cmd &= 0x7Fu;
    resp = sd_send_cmd(SD_CMD55, 0);
    if (resp > 1u) {
      return resp;
    }
  }

  sd_deselect();
  sd_spi_clock();
  sd_select();

  if (!sd_wait_ready(SD_SPI_TIMEOUT_MS)) {
    sd_deselect();
    return 0xFFu;
  }

  if (cmd == SD_CMD0) {
    crc = 0x95;
  } else if (cmd == SD_CMD8) {
    crc = 0x87;
  }

  sd_spi_txrx((BYTE)(0x40u | cmd));
  sd_spi_txrx((BYTE)(arg >> 24));
  sd_spi_txrx((BYTE)(arg >> 16));
  sd_spi_txrx((BYTE)(arg >> 8));
  sd_spi_txrx((BYTE)arg);
  sd_spi_txrx(crc);

  if (cmd == SD_CMD12) {
    sd_spi_clock();
  }

  for (uint8_t i = 0; i < 10; ++i) {
    resp = sd_spi_txrx(SD_DUMMY_BYTE);
    if ((resp & 0x80u) == 0u) {
      return resp;
    }
  }

  return 0xFFu;
}

static int sd_receive_datablock(BYTE *buff, UINT btr)
{
  BYTE token;
  uint32_t start = HAL_GetTick();

  do {
    token = sd_spi_txrx(SD_DUMMY_BYTE);
    if (token == SD_TOKEN_START_BLOCK) {
      break;
    }
  } while ((HAL_GetTick() - start) < SD_SPI_TIMEOUT_MS);

  if (token != SD_TOKEN_START_BLOCK) {
    return 0;
  }

  while (btr--) {
    *buff++ = sd_spi_txrx(SD_DUMMY_BYTE);
  }

  sd_spi_clock(); /* discard CRC */
  sd_spi_clock();
  return 1;
}

#if _USE_WRITE == 1
static int sd_transmit_datablock(const BYTE *buff, BYTE token)
{
  BYTE resp;

  if (!sd_wait_ready(SD_SPI_TIMEOUT_MS)) {
    return 0;
  }

  sd_spi_txrx(token);
  if (token == SD_TOKEN_STOP_TRAN) {
    return 1;
  }

  for (UINT i = 0; i < 512u; ++i) {
    sd_spi_txrx(buff[i]);
  }

  sd_spi_clock(); /* dummy CRC */
  sd_spi_clock();

  resp = sd_spi_txrx(SD_DUMMY_BYTE);
  if ((resp & 0x1Fu) != SD_DATA_ACCEPTED) {
    return 0;
  }

  return 1;
}
#endif

#if _USE_IOCTL == 1
static DWORD sd_sector_count_from_csd(const BYTE csd[16])
{
  DWORD csize;

  if ((csd[0] >> 6) == 1u) {
    csize = ((DWORD)(csd[7] & 0x3Fu) << 16)
          | ((DWORD)csd[8] << 8)
          | csd[9];
    return (csize + 1u) << 10;
  }

  BYTE read_bl_len = csd[5] & 0x0Fu;
  WORD c_size = (WORD)(((csd[6] & 0x03u) << 10)
                | ((WORD)csd[7] << 2)
                | ((csd[8] & 0xC0u) >> 6));
  BYTE c_size_mult = (BYTE)(((csd[9] & 0x03u) << 1)
                     | ((csd[10] & 0x80u) >> 7));
  DWORD blocknr = (DWORD)(c_size + 1u) << (c_size_mult + 2u);
  DWORD block_len = 1UL << read_bl_len;
  return blocknr * (block_len / 512u);
}
#endif

/* USER CODE END DECL */

/* Private function prototypes -----------------------------------------------*/
DSTATUS USER_initialize (BYTE pdrv);
DSTATUS USER_status (BYTE pdrv);
DRESULT USER_read (BYTE pdrv, BYTE *buff, DWORD sector, UINT count);
#if _USE_WRITE == 1
  DRESULT USER_write (BYTE pdrv, const BYTE *buff, DWORD sector, UINT count);
#endif /* _USE_WRITE == 1 */
#if _USE_IOCTL == 1
  DRESULT USER_ioctl (BYTE pdrv, BYTE cmd, void *buff);
#endif /* _USE_IOCTL == 1 */

Diskio_drvTypeDef  USER_Driver =
{
  USER_initialize,
  USER_status,
  USER_read,
#if  _USE_WRITE
  USER_write,
#endif  /* _USE_WRITE == 1 */
#if  _USE_IOCTL == 1
  USER_ioctl,
#endif /* _USE_IOCTL == 1 */
};

/* Private functions ---------------------------------------------------------*/

/**
  * @brief  Initializes a Drive
  * @param  pdrv: Physical drive number (0..)
  * @retval DSTATUS: Operation status
  */
DSTATUS USER_initialize (
	BYTE pdrv           /* Physical drive nmuber to identify the drive */
)
{
  /* USER CODE BEGIN INIT */
  BYTE n;
  BYTE ty = 0;
  BYTE ocr[4];
  uint32_t start;

  if (pdrv != 0u) {
    return STA_NOINIT;
  }

  sd_power_on_clocks();

  if (sd_send_cmd(SD_CMD0, 0) == 1u) {
    start = HAL_GetTick();

    if (sd_send_cmd(SD_CMD8, 0x1AAu) == 1u) {
      for (n = 0; n < 4u; ++n) {
        ocr[n] = sd_spi_txrx(SD_DUMMY_BYTE);
      }

      if (ocr[2] == 0x01u && ocr[3] == 0xAAu) {
        do {
          if (sd_send_cmd(0x80u | SD_ACMD41, 0x40000000u) == 0u) {
            break;
          }
        } while ((HAL_GetTick() - start) < 1000u);

        if ((HAL_GetTick() - start) < 1000u && sd_send_cmd(SD_CMD58, 0) == 0u) {
          for (n = 0; n < 4u; ++n) {
            ocr[n] = sd_spi_txrx(SD_DUMMY_BYTE);
          }
          ty = (ocr[0] & 0x40u) ? (CT_SD2 | CT_BLOCK) : CT_SD2;
        }
      }
    } else {
      if (sd_send_cmd(0x80u | SD_ACMD41, 0) <= 1u) {
        ty = CT_SD1;
        start = HAL_GetTick();
        do {
          if (sd_send_cmd(0x80u | SD_ACMD41, 0) == 0u) {
            break;
          }
        } while ((HAL_GetTick() - start) < 1000u);
      } else {
        ty = CT_MMC;
        start = HAL_GetTick();
        do {
          if (sd_send_cmd(SD_CMD1, 0) == 0u) {
            break;
          }
        } while ((HAL_GetTick() - start) < 1000u);
      }

      if ((HAL_GetTick() - start) >= 1000u || sd_send_cmd(SD_CMD16, 512u) != 0u) {
        ty = 0;
      }
    }
  }

  CardType = ty;
  sd_deselect();
  sd_spi_clock();

  Stat = ty ? 0u : STA_NOINIT;
  return Stat;
  /* USER CODE END INIT */
}

/**
  * @brief  Gets Disk Status
  * @param  pdrv: Physical drive number (0..)
  * @retval DSTATUS: Operation status
  */
DSTATUS USER_status (
	BYTE pdrv       /* Physical drive number to identify the drive */
)
{
  /* USER CODE BEGIN STATUS */
  if (pdrv != 0u) {
    return STA_NOINIT;
  }
  return Stat;
  /* USER CODE END STATUS */
}

/**
  * @brief  Reads Sector(s)
  * @param  pdrv: Physical drive number (0..)
  * @param  *buff: Data buffer to store read data
  * @param  sector: Sector address (LBA)
  * @param  count: Number of sectors to read (1..128)
  * @retval DRESULT: Operation result
  */
DRESULT USER_read (
	BYTE pdrv,      /* Physical drive nmuber to identify the drive */
	BYTE *buff,     /* Data buffer to store read data */
	DWORD sector,   /* Sector address in LBA */
	UINT count      /* Number of sectors to read */
)
{
  /* USER CODE BEGIN READ */
  if (pdrv != 0u || count == 0u) {
    return RES_PARERR;
  }
  if (Stat & STA_NOINIT) {
    return RES_NOTRDY;
  }

  if (!(CardType & CT_BLOCK)) {
    sector *= 512u;
  }

  if (count == 1u) {
    if (sd_send_cmd(SD_CMD17, sector) == 0u && sd_receive_datablock(buff, 512u)) {
      count = 0u;
    }
  } else {
    if (sd_send_cmd(SD_CMD18, sector) == 0u) {
      do {
        if (!sd_receive_datablock(buff, 512u)) {
          break;
        }
        buff += 512u;
      } while (--count);
      (void)sd_send_cmd(SD_CMD12, 0);
    }
  }

  sd_deselect();
  sd_spi_clock();
  return count ? RES_ERROR : RES_OK;
  /* USER CODE END READ */
}

/**
  * @brief  Writes Sector(s)
  * @param  pdrv: Physical drive number (0..)
  * @param  *buff: Data to be written
  * @param  sector: Sector address (LBA)
  * @param  count: Number of sectors to write (1..128)
  * @retval DRESULT: Operation result
  */
#if _USE_WRITE == 1
DRESULT USER_write (
	BYTE pdrv,          /* Physical drive nmuber to identify the drive */
	const BYTE *buff,   /* Data to be written */
	DWORD sector,       /* Sector address in LBA */
	UINT count          /* Number of sectors to write */
)
{
  /* USER CODE BEGIN WRITE */
  if (pdrv != 0u || count == 0u) {
    return RES_PARERR;
  }
  if (Stat & STA_NOINIT) {
    return RES_NOTRDY;
  }

  if (!(CardType & CT_BLOCK)) {
    sector *= 512u;
  }

  if (count == 1u) {
    if (sd_send_cmd(SD_CMD24, sector) == 0u
        && sd_transmit_datablock(buff, SD_TOKEN_START_BLOCK)) {
      count = 0u;
    }
  } else {
    if (sd_send_cmd(SD_CMD25, sector) == 0u) {
      do {
        if (!sd_transmit_datablock(buff, SD_TOKEN_MULTI_WRITE)) {
          break;
        }
        buff += 512u;
      } while (--count);
      if (!sd_transmit_datablock(0, SD_TOKEN_STOP_TRAN)) {
        count = 1u;
      }
    }
  }

  sd_deselect();
  sd_spi_clock();
  return count ? RES_ERROR : RES_OK;
  /* USER CODE END WRITE */
}
#endif /* _USE_WRITE == 1 */

/**
  * @brief  I/O control operation
  * @param  pdrv: Physical drive number (0..)
  * @param  cmd: Control code
  * @param  *buff: Buffer to send/receive control data
  * @retval DRESULT: Operation result
  */
#if _USE_IOCTL == 1
DRESULT USER_ioctl (
	BYTE pdrv,      /* Physical drive nmuber (0..) */
	BYTE cmd,       /* Control code */
	void *buff      /* Buffer to send/receive control data */
)
{
  /* USER CODE BEGIN IOCTL */
  BYTE csd[16];
  DRESULT res = RES_ERROR;

  if (pdrv != 0u) {
    return RES_PARERR;
  }
  if (Stat & STA_NOINIT) {
    return RES_NOTRDY;
  }

  switch (cmd) {
  case CTRL_SYNC:
    sd_select();
    res = sd_wait_ready(SD_SPI_TIMEOUT_MS) ? RES_OK : RES_ERROR;
    break;

  case GET_SECTOR_COUNT:
    if (buff != 0 && sd_send_cmd(SD_CMD9, 0) == 0u && sd_receive_datablock(csd, 16u)) {
      *(DWORD*)buff = sd_sector_count_from_csd(csd);
      res = RES_OK;
    }
    break;

  case GET_SECTOR_SIZE:
    if (buff != 0) {
      *(WORD*)buff = 512u;
      res = RES_OK;
    }
    break;

  case GET_BLOCK_SIZE:
    if (buff != 0) {
      *(DWORD*)buff = 1u;
      res = RES_OK;
    }
    break;

  default:
    res = RES_PARERR;
    break;
  }

  sd_deselect();
  sd_spi_clock();
  return res;
  /* USER CODE END IOCTL */
}
#endif /* _USE_IOCTL == 1 */

