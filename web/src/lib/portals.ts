// Typed access to content/portals.json (CONTRACTS §9/§7, read-only).
import data from '@content/portals.json';

export interface PortalDef {
  url: string;
  phone?: string;
  source?: string;
}

export interface ActionDef {
  kind: 'call' | 'portal' | 'route' | 'share' | 'info';
  phone?: string;
  portal?: string;
  route?: string;
}

interface PortalsFile {
  portals: Record<string, PortalDef>;
  actions: Record<string, ActionDef>;
}

const portalsData = data as unknown as PortalsFile;

export function resolveAction(id: string): ActionDef | undefined {
  return portalsData.actions[id];
}

export function resolvePortal(id: string | undefined): PortalDef | undefined {
  return id ? portalsData.portals[id] : undefined;
}
