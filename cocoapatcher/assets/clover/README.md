# Clover bootloader (MBR / legacy UEFI chainload)

Place a licensed **Clover** `BOOTX64.EFI` here for MBR USB creation with OpenCore chainloading.

cocoapatcher copies this file to the USB root (`BOOTX64.EFI`) and writes `EFI/CLOVER/config.plist` with a custom entry pointing to `\EFI\OC\OpenCore.efi`.

## Obtain Clover

Build from [CloverHackyColor/CloverBootloader](https://github.com/CloverHackyColor/CloverBootloader) or use a known-good release build. Respect Clover's license.

## Override

Set environment variable `CLOVER_BOOTX64` to an absolute path to `BOOTX64.EFI` if you do not bundle it in this folder.

If no Clover binary is present, MBR mode falls back to standard OpenCore GPT layout only (OpenCore at `EFI/BOOT/BOOTX64.EFI`).
