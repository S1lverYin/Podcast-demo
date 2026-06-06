const TIMEZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function parseServerDate(value: string): Date {
  return new Date(TIMEZONE_SUFFIX_RE.test(value) ? value : `${value}Z`);
}
