// Screenshot handling (LLD §22.1): client-side compression keeps uploads near 150 KB and strips
// EXIF (location) by re-encoding; QR decoding runs locally so a payment QR never needs OCR.

export const MAX_SIDE = 1280;
export const JPEG_QUALITY = 0.7;

/** createImageBitmap -> canvas at longest-side `maxSide` -> JPEG. Re-encoding drops EXIF GPS data. */
export async function compressImage(file: Blob, maxSide = MAX_SIDE, quality = JPEG_QUALITY): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, width, height);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('toBlob failed'))), 'image/jpeg', quality);
    });
  } finally {
    bitmap.close();
  }
}

export function isQrSupported(): boolean {
  return typeof window !== 'undefined' && !!window.BarcodeDetector;
}

/** Decodes a QR from an image/frame; null when unsupported or nothing found (never throws). */
export async function decodeQr(image: ImageBitmapSource): Promise<string | null> {
  if (!isQrSupported()) return null;
  try {
    const detector = new window.BarcodeDetector!({ formats: ['qr_code'] });
    const results = await detector.detect(image);
    return results[0]?.rawValue ?? null;
  } catch {
    return null;
  }
}
