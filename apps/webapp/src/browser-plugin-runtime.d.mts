export interface BrowserRecord {
  id: string;
  name: string;
  description?: string;
  digest: string;
  approved: boolean;
  profile: string;
  principal: string;
  status: "disabled" | "loaded" | "error";
  error?: string;
  dispose: (() => void) | null;
}
export interface RuntimeOptions {
  evaluationTimeoutMs?: number;
  scope: () => string;
  request: (url: string) => Promise<any>;
  reserved: (id: string) => boolean;
  drop: (id: string) => void;
  report?: (error: unknown) => void;
  publish: (record: BrowserRecord) => void;
  evaluate: (
    source: string,
    record: BrowserRecord,
    alive: () => boolean,
  ) => Promise<any>;
  activate: (
    record: BrowserRecord,
    module: any,
    alive: () => boolean,
  ) => Promise<() => void>;
}
export class BrowserPluginRuntime {
  constructor(options: RuntimeOptions);
  records: Map<string, BrowserRecord>;
  reset(): void;
  scan(): Promise<void>;
  enable(id: string): Promise<void>;
  disable(id: string): void;
}
export function verifySnapshot(
  snapshot: unknown,
  expected: unknown,
): Promise<string>;
