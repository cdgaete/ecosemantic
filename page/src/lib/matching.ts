function folded(text: string): string {
  return text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

function words(text: string): string[] {
  return folded(text).split(/[^\p{L}\p{N}]+/u).filter((word) => word.length > 0)
}

export function beginsAWord(query: string, shown: string[]): boolean {
  const asked = words(query)
  const offered = shown.flatMap(words)
  return asked.every((word) => offered.some((candidate) => candidate.startsWith(word)))
}
