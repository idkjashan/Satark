import { describe, it, expect, vi, afterEach } from 'vitest';
import { compressImage } from './image';

// happy-dom's <canvas> has no real rasteriser, so we stand in a fake one: this tests the resize
// maths and the toBlob() call (type/quality), not actual pixel output.
function stubCanvas() {
  const drawImage = vi.fn();
  const toBlob = vi.fn((cb: (b: Blob | null) => void, type?: string) => {
    cb(new Blob(['jpeg-bytes'], { type: type ?? 'image/jpeg' }));
  });
  const fakeCanvas = { width: 0, height: 0, getContext: vi.fn(() => ({ drawImage })), toBlob };
  vi.spyOn(document, 'createElement').mockReturnValue(fakeCanvas as unknown as HTMLCanvasElement);
  return { fakeCanvas, drawImage, toBlob };
}

function stubBitmap(width: number, height: number) {
  const bitmap = { width, height, close: vi.fn() };
  vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap));
  return bitmap;
}

describe('compressImage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('scales the longest side down to maxSide and keeps the aspect ratio', async () => {
    const bitmap = stubBitmap(4000, 2000); // a wide screenshot
    const { fakeCanvas, drawImage } = stubCanvas();

    await compressImage(new Blob(), 1280, 0.7);

    expect(fakeCanvas.width).toBe(1280);
    expect(fakeCanvas.height).toBe(640); // 2000/4000 * 1280
    expect(drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 1280, 640);
    expect(bitmap.close).toHaveBeenCalled();
  });

  it('never upscales an image already smaller than maxSide', async () => {
    stubBitmap(300, 200);
    const { fakeCanvas } = stubCanvas();

    await compressImage(new Blob(), 1280, 0.7);

    expect(fakeCanvas.width).toBe(300);
    expect(fakeCanvas.height).toBe(200);
  });

  it('encodes as JPEG at the requested quality', async () => {
    stubBitmap(800, 600);
    const { toBlob } = stubCanvas();

    const result = await compressImage(new Blob(), 1280, 0.7);

    expect(toBlob).toHaveBeenCalledWith(expect.any(Function), 'image/jpeg', 0.7);
    expect(result.type).toBe('image/jpeg');
  });

  it('falls back to the original file when 2D canvas context is unavailable', async () => {
    stubBitmap(800, 600);
    const fakeCanvas = { width: 0, height: 0, getContext: vi.fn(() => null), toBlob: vi.fn() };
    vi.spyOn(document, 'createElement').mockReturnValue(fakeCanvas as unknown as HTMLCanvasElement);
    const original = new Blob(['original'], { type: 'image/png' });

    const result = await compressImage(original);

    expect(result).toBe(original);
  });
});
