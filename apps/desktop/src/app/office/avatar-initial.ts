/** First letter / CJK character for chibi head badges. */
export function avatarInitial(text: string): string {
  const trimmed = (text || '').trim()
  if (!trimmed) return '?'

  const match = trimmed.match(/\p{Script=Han}|\p{L}|\p{N}/u)
  const ch = match?.[0] ?? trimmed[0] ?? '?'

  return ch.toUpperCase()
}
