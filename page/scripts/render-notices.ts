export type Notice = {
  name: string
  version: string
  license: string
  homepage: string | undefined
  texts: string[]
}

const RULE = '-'.repeat(72)

function entry(notice: Notice): string {
  const head = [`${notice.name} ${notice.version} (${notice.license})`, notice.homepage].filter(Boolean).join('\n')
  const body = notice.texts.length
    ? notice.texts.map((text) => text.trim()).join('\n\n')
    : `The package carries no licence file; its package.json names ${notice.license}.`
  return `${RULE}\n${head}\n\n${body}\n`
}

export function render(notices: Notice[]): string {
  const sorted = [...notices].sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version))
  return [
    'Third-party software in the EcoSemantic page\n',
    'The page that ecosemantic-view carries bundles the packages below, each with its version,',
    'the licence its package.json names and the licence text the package carries.\n',
    ...sorted.map(entry),
  ].join('\n')
}
