// Ambient types for browser APIs not yet in TypeScript's bundled DOM lib.
// Both are feature-detected at every call site; these declarations only describe
// the shape once presence is confirmed.

interface BarcodeDetectorOptions {
  formats: string[];
}

interface DetectedBarcode {
  rawValue: string;
}

declare class BarcodeDetector {
  constructor(options?: BarcodeDetectorOptions);
  detect(image: ImageBitmapSource): Promise<DetectedBarcode[]>;
  static getSupportedFormats(): Promise<string[]>;
}

interface SpeechRecognitionResultLike {
  [index: number]: { transcript: string };
  isFinal?: boolean;
}
interface SpeechRecognitionEventLike extends Event {
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface Window {
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  BarcodeDetector?: typeof BarcodeDetector;
}
