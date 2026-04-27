export type TimestampParseResult =
  | { kind: 'empty'; value: null }
  | { kind: 'valid'; value: number }
  | { kind: 'invalid'; reason: string; value: null }

export function parseTimestampInput(raw: string): TimestampParseResult {
  const trimmed = raw.trim()
  if (!trimmed) {
    return { kind: 'empty', value: null }
  }
  const numeric = Number(trimmed)
  if (!Number.isFinite(numeric)) {
    return { kind: 'invalid', reason: 'Timestamp must be a finite number.', value: null }
  }
  if (numeric < 0) {
    return { kind: 'invalid', reason: 'Timestamp must be zero or greater.', value: null }
  }
  return { kind: 'valid', value: Math.round(numeric) }
}
