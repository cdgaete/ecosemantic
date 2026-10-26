import { execFileSync } from 'node:child_process'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'
import { render, type Notice } from './render-notices.ts'

type Listed = { name: string; versions: string[]; paths: string[]; license: string; homepage?: string }

const here = path.dirname(url.fileURLToPath(import.meta.url))
const LICENCE_FILE = /^(licen[cs]e|copying|notice)(\.[a-z]+)?$/i
const TARGET = path.resolve(here, '../../view/ecosemantic/view/static/THIRD_PARTY_NOTICES.txt')

function texts(directory: string): string[] {
  return readdirSync(directory)
    .filter((name) => LICENCE_FILE.test(name))
    .sort()
    .map((name) => readFileSync(path.join(directory, name), 'utf8'))
}

const listed = JSON.parse(
  execFileSync('pnpm', ['licenses', 'list', '--prod', '--json'], { cwd: path.resolve(here, '..'), encoding: 'utf8' }),
) as Record<string, Listed[]>
const notices: Notice[] = Object.values(listed)
  .flat()
  .flatMap((pkg) =>
    pkg.versions.map((version, index) => ({
      name: pkg.name,
      version,
      license: pkg.license,
      homepage: pkg.homepage,
      texts: texts(pkg.paths[index]),
    })),
  )
writeFileSync(TARGET, render(notices))
console.log(`wrote ${notices.length} notices to ${path.relative(process.cwd(), TARGET)}`)
