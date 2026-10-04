// /check (CONTRACTS §6 `POST /v1/checks`, LLD §22.1/§22.2): paste, screenshot, camera QR, or
// mic dictation, then submit. Also the landing point for the share target (`?share=<id>`, read
// from IndexedDB and deleted) and the server-side share fallback (`?text=...`).
import { useEffect, useRef } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { compressImage, decodeQr, isQrSupported } from '../lib/image';
import { isDictationSupported, startDictation } from '../lib/speechInput';
import { takeSharePayload } from '../lib/idb';
import { postCheck, lastCheckInput, ApiError } from '../lib/api';
import { Icon } from '../components/Icon';
import { CheckArt } from '../components/Illustrations';

export function Check() {
  const { query, route } = useLocation();
  const text = useSignal('');
  const imageBlob = useSignal<Blob | null>(null);
  const imagePreview = useSignal<string | null>(null);
  const qr = useSignal<string | null>(null);
  const submitting = useSignal(false);
  const errorMsg = useSignal<string | null>(null);
  const scanning = useSignal(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scanTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dictationRef = useRef<ReturnType<typeof startDictation>>(null);

  // Share-target landing: read-and-delete the service worker's payload, or the server's
  // `?text=` fallback when the SW wasn't active to intercept the share.
  useEffect(() => {
    const shareId = query.share;
    if (shareId) {
      void takeSharePayload(shareId).then(async (payload) => {
        if (!payload) return;
        text.value = [payload.text, payload.url].filter(Boolean).join('\n') || payload.title || '';
        const file = payload.files?.[0];
        if (file) await handleFile(file);
      });
    } else if (query.text) {
      text.value = query.text;
    }
    return () => {
      if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
      stopScan();
    };
    // Intentionally run once per mount only: the share/text query hand-off is one-shot.
  }, []);

  async function handleFile(file: Blob) {
    const compressed = await compressImage(file);
    if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
    imageBlob.value = compressed;
    imagePreview.value = URL.createObjectURL(compressed);
    const decoded = await decodeQr(await createImageBitmap(compressed));
    if (decoded) qr.value = decoded;
  }

  function stopScan() {
    if (scanTimerRef.current) clearInterval(scanTimerRef.current);
    scanTimerRef.current = null;
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
    scanning.value = false;
  }

  async function startScan() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      scanning.value = true;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      scanTimerRef.current = setInterval(async () => {
        if (!videoRef.current) return;
        const decoded = await decodeQr(videoRef.current);
        if (decoded) {
          qr.value = decoded;
          stopScan();
        }
      }, 400);
    } catch {
      errorMsg.value = t('ui.camera_unavailable');
    }
  }

  function toggleMic() {
    if (dictationRef.current) {
      dictationRef.current.stop();
      dictationRef.current = null;
      return;
    }
    // Interim results arrive as a running transcript for this turn only; re-anchor each update
    // to the text already there before this mic press, so live words replace cleanly instead of
    // piling up on every partial update.
    const base = text.value;
    dictationRef.current = startDictation(
      prefs.value.lang,
      (heard) => {
        text.value = base ? `${base} ${heard}` : heard;
      },
      () => {
        dictationRef.current = null;
      },
    );
  }

  async function submit() {
    if (!text.value.trim() && !imageBlob.value) {
      errorMsg.value = t('ui.nothing_to_check');
      return;
    }
    submitting.value = true;
    errorMsg.value = null;
    const input = {
      text: text.value.trim() || undefined,
      image: imageBlob.value ?? undefined,
      qr: qr.value ?? undefined,
      lang: prefs.value.lang,
      simple: prefs.value.simple,
    };
    lastCheckInput.value = input;
    try {
      const handle = await postCheck(input);
      route(`/run/${handle.run_id}?case=${handle.case_id}`);
    } catch (err) {
      // content.<lang>.json keys its error strings "error.<code>" (e.g. error.run_not_found),
      // matching the bare `code` field CONTRACTS documents - not necessarily `message_key` as-is.
      errorMsg.value = t(`error.${err instanceof ApiError ? err.code : 'internal'}`);
    } finally {
      submitting.value = false;
    }
  }

  return (
    <main class="screen screen-wide check-screen">
      <header class="page-head">
        <CheckArt class="page-art" />
        <h1>{t('ui.check_a_message')}</h1>
        <p class="lead">{t('ui.check_sub')}</p>
      </header>

      <div class="check-columns">
        <div class="check-input-col">
          <div class="composer-card">
            <textarea
              class="check-textarea"
              data-testid="check-input"
              rows={6}
              aria-label={t('ui.paste_placeholder')}
              placeholder={t('ui.paste_placeholder')}
              value={text.value}
              onInput={(e) => (text.value = (e.target as HTMLTextAreaElement).value)}
            />

            <div class="composer-tools">
              <button type="button" class="tool-btn" data-testid="check-image" onClick={() => fileInputRef.current?.click()}>
                <Icon name="upload" size={18} /> {t('ui.pick_screenshot')}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = (e.target as HTMLInputElement).files?.[0];
                  if (file) void handleFile(file);
                }}
              />
              {isQrSupported() && !scanning.value && (
                <button type="button" class="tool-btn" onClick={() => void startScan()}>
                  <Icon name="qrcode" size={18} /> {t('ui.scan_qr')}
                </button>
              )}
              {isDictationSupported() && (
                <button type="button" class="btn-mic tool-btn" aria-label={t('ui.mic')} onClick={toggleMic}>
                  <Icon name="mic" size={18} /> {t('ui.dictate')}
                </button>
              )}
            </div>
            {isDictationSupported() && <p class="mic-disclosure">{t('ui.mic_disclosure')}</p>}
          </div>

          {scanning.value && (
            <div class="qr-scanner">
              <video ref={videoRef} muted playsInline />
              <button type="button" class="btn" onClick={stopScan}>
                {t('ui.cancel')}
              </button>
            </div>
          )}

          {imagePreview.value && (
            <div class="image-preview">
              <img src={imagePreview.value} alt={t('ui.screenshot_preview')} />
              <button
                type="button"
                class="btn"
                onClick={() => {
                  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
                  imageBlob.value = null;
                  imagePreview.value = null;
                  qr.value = null;
                }}
              >
                {t('ui.remove')}
              </button>
            </div>
          )}

          {qr.value && <p class="qr-found">{t('ui.qr_found')}</p>}
          {errorMsg.value && (
            <p role="alert" class="error-banner">
              <Icon name="alertCircle" size={18} /> {errorMsg.value}
            </p>
          )}

          <button
            type="button"
            class="btn btn-primary btn-huge"
            data-testid="check-submit"
            disabled={submitting.value}
            onClick={() => void submit()}
          >
            {submitting.value ? <Icon name="loader" size={20} spin /> : <Icon name="check" size={20} />}
            {submitting.value ? t('ui.checking') : t('ui.check_a_message')}
          </button>

          <div class="example-row">
            <span class="example-label">{t('ui.try_example_label')}</span>
            <button type="button" class="chip" onClick={() => (text.value = t('ui.example_scam_text'))}>
              {t('ui.try_scam_example')}
            </button>
            <button type="button" class="chip" onClick={() => (text.value = t('ui.example_genuine_text'))}>
              {t('ui.try_genuine_example')}
            </button>
          </div>

          <p class="share-hint">
            <Icon name="share" size={16} /> {t('ui.share_hint')}
          </p>
        </div>

        <aside class="check-tips-col">
          <h2>{t('ui.check_tips_title')}</h2>
          <ul class="check-tips-list">
            <li>
              <Icon name="landmark" size={18} /> {t('ui.check_tip_registry')}
            </li>
            <li>
              <Icon name="qrcode" size={18} /> {t('ui.check_tip_link')}
            </li>
            <li>
              <Icon name="phone" size={18} /> {t('ui.check_tip_upi')}
            </li>
            <li>
              <Icon name="lock" size={18} /> {t('ui.check_tip_never')}
            </li>
          </ul>
        </aside>
      </div>
    </main>
  );
}
