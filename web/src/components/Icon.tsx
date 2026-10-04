// One icon set for the whole app: Lucide (lucide-preact, ISC licence - the same icon set shadcn/ui
// uses), imported by name so only the glyphs listed here reach the bundle. Icons are always
// `aria-hidden` decoration beside a visible text label (nav items, buttons), never the only cue.
import type { ComponentType } from 'preact';
import {
  ArrowRight,
  BadgeCheck,
  BookOpen,
  Briefcase,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Clapperboard,
  ClipboardPaste,
  Crosshair,
  FileText,
  Flag,
  FlaskConical,
  Gauge,
  Globe,
  HeartCrack,
  History,
  House,
  Info,
  KeyRound,
  Landmark,
  LoaderCircle,
  Lock,
  Megaphone,
  MessageCircle,
  Mic,
  Moon,
  Newspaper,
  Phone,
  ScanLine,
  SendHorizontal,
  Settings,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Siren,
  Smartphone,
  Sun,
  ThumbsUp,
  TrendingUp,
  TriangleAlert,
  Upload,
  Volume2,
  Wallet,
  WifiOff,
  X,
} from 'lucide-preact';

const ICONS = {
  home: House,
  check: ShieldCheck,
  chat: MessageCircle,
  learn: BookOpen,
  practice: FlaskConical,
  back: ChevronLeft,
  phone: Phone,
  mic: Mic,
  speaker: Volume2,
  sun: Sun,
  moon: Moon,
  globe: Globe,
  history: History,
  close: X,
  thumbUp: ThumbsUp,
  flag: Flag,
  wifiOff: WifiOff,
  chevronRight: ChevronRight,
  share: Share2,
  camera: Camera,
  qrcode: ScanLine,
  warningTriangle: TriangleAlert,
  alertCircle: CircleAlert,
  checkCircle: CircleCheck,
  helpCircle: CircleHelp,
  loader: LoaderCircle,
  send: SendHorizontal,
  settings: Settings,
  arrowRight: ArrowRight,
  upload: Upload,
  paste: ClipboardPaste,
  landmark: Landmark,
  info: Info,
  lock: Lock,
  news: Newspaper,
  tick: Check,
  tactic: Crosshair,
  shieldAlert: ShieldAlert,
  // lesson topics (Learn.tsx maps lesson ids onto these)
  trendingUp: TrendingUp,
  video: Clapperboard,
  siren: Siren,
  phoneApp: Smartphone,
  document: FileText,
  job: Briefcase,
  key: KeyRound,
  gauge: Gauge,
  heartCrack: HeartCrack,
  badge: BadgeCheck,
  megaphone: Megaphone,
  wallet: Wallet,
} satisfies Record<string, ComponentType<{ size?: number; strokeWidth?: number; 'aria-hidden'?: boolean }>>;

export type IconName = keyof typeof ICONS;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  /** Rotation for the "checking..." row; a no-op under prefers-reduced-motion (global rule in styles.css). */
  spin?: boolean;
  /** Kept for call-site compatibility: draws the glyph on a soft tinted square. */
  badge?: boolean;
}

export function Icon({ name, size = 20, className, spin, badge }: IconProps) {
  const Glyph = ICONS[name];
  const classes = ['icon', spin ? 'icon-spin' : '', badge ? 'icon-badge' : '', className ?? ''].filter(Boolean).join(' ');
  return (
    <span class={classes} style={badge ? { width: size * 1.6, height: size * 1.6 } : undefined} aria-hidden="true">
      <Glyph size={size} strokeWidth={2} aria-hidden={true} />
    </span>
  );
}
