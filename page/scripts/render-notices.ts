import { readFileSync } from 'node:fs'
import * as path from 'node:path'

export type Notice = {
  name: string
  version: string
  license: string
  homepage: string | undefined
  texts: string[]
}

type Font = { name: string; version: string; licence: string }

const FONTS: Font[] = [
  { name: 'Source Sans 3', version: '3.052', licence: 'OFL-SourceSans3.txt' },
  { name: 'JetBrains Mono', version: '2.211', licence: 'OFL-JetBrainsMono.txt' },
]

const RULE = '-'.repeat(72)

export function fontNotices(directory: string): Notice[] {
  return FONTS.map((font) => ({
    name: font.name,
    version: font.version,
    license: 'OFL-1.1',
    homepage: undefined,
    texts: [readFileSync(path.join(directory, font.licence), 'utf8')],
  }))
}

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
    'The page that ecosemantic-view carries bundles the software below, each with its version,',
    'the licence it is under and the licence text it carries.\n',
    ...sorted.map(entry),
  ].join('\n')
}
