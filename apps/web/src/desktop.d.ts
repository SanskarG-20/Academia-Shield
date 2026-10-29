interface Window {
  academiaDesktop?: {
    enrollAgent: (claim: string) => Promise<{ ok: boolean; error?: string }>;
  };
}
