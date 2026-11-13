/// <reference types="node" />
import { readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'

import impact from './fixtures/impact.json'
import impactMonteCarlo from './fixtures/impact_monte_carlo.json'
import panelImpactMonteCarlo from './fixtures/panel_impact_monte_carlo.json'
import byProcess from './fixtures/contributions_process.json'
import byFlow from './fixtures/contributions_flow.json'
import byPath from './fixtures/contributions_path.json'
import inventory from './fixtures/inventory.json'

type Render = (content: unknown) => void

const here = path.dirname(url.fileURLToPath(import.meta.url))
const PANELS = path.resolve(here, '../../mcp/ecosemantic/mcp/panels')

function openPanel(name: string): Render {
  const source = readFileSync(path.join(PANELS, `${name}.html`), 'utf8')
  const script = /<script>([\s\S]*)<\/script>/.exec(source)?.[1] ?? ''
  const body = /<body>([\s\S]*)<\/body>/.exec(source)?.[1] ?? ''
  document.body.innerHTML = body.replace(/<script>[\s\S]*<\/script>/, '')
  const panel = new Function(`${script}\nreturn { render }`)() as { render: Render }
  return panel.render
}

function texts(selector: string): string[] {
  return Array.from(document.querySelectorAll(selector), (element) => element.textContent ?? '')
}

function count(selector: string): number {
  return document.querySelectorAll(selector).length
}

function fmt(value: number): string {
  return Number(value).toLocaleString(undefined, { maximumSignificantDigits: 4 })
}

function specsOf(methods: { id: string; spec: string }[]): Map<string, string> {
  return new Map(methods.map((method) => [method.id, method.spec]))
}

it('draws a row for every score of an impact answer, each named by its method spec', () => {
  const render = openPanel('impact')
  render(impact)
  const specs = specsOf(impact.value.methods)
  const scores = impact.value.scores
  expect(texts('#view tr td:first-child')).toEqual(scores.map((score) => specs.get(score.method_id)))
  expect(texts('#view tr td:last-child')).toEqual(
    scores.map((score) => `${fmt(score.value)} ${score.unit}`),
  )
  expect(texts('#title')).toEqual([`Impact of ${impact.value.product_system}`])
})

it('draws a paragraph naming each category and twenty bars from its histogram when the answer carries no samples', () => {
  const render = openPanel('impact')
  const uncertainty = panelImpactMonteCarlo.value.uncertainty
  const specs = specsOf(panelImpactMonteCarlo.value.methods)
  expect(uncertainty.categories).not.toHaveLength(0)
  uncertainty.categories.forEach((category) => expect(category.samples).toBeNull())
  render(panelImpactMonteCarlo)
  expect(count('#view p')).toBe(uncertainty.categories.length)
  expect(count('#view svg')).toBe(uncertainty.categories.length)
  uncertainty.categories.forEach((category, i) => {
    expect(texts('#view p')[i]).toContain(specs.get(category.method_id))
    expect(texts('#view p')[i]).toContain(`n ${category.summary.n}`)
    const bars = document.querySelectorAll('#view svg')[i].querySelectorAll('rect')
    expect(bars).toHaveLength(20)
  })
})

it('draws twenty bars for each category of an answer that carries its samples', () => {
  const render = openPanel('impact')
  const uncertainty = impactMonteCarlo.value.uncertainty
  expect(uncertainty.categories).not.toHaveLength(0)
  uncertainty.categories.forEach((category) => expect(category.histogram).toBeNull())
  render(impactMonteCarlo)
  expect(count('#view svg')).toBe(uncertainty.categories.length)
  Array.from(document.querySelectorAll('#view svg')).forEach((svg) => {
    expect(svg.querySelectorAll('rect')).toHaveLength(20)
  })
})

it('draws a column for each variant when the answer carries variants and no uncertainty', () => {
  // a call with variants and no monte_carlo block: the recorded value without its uncertainty
  const answer = structuredClone(panelImpactMonteCarlo) as unknown as {
    value: { uncertainty?: unknown; variants: { name: string; uncertainty?: unknown }[] }
    view_url: string | null
  }
  delete answer.value.uncertainty
  answer.value.variants.forEach((variant) => delete variant.uncertainty)
  const render = openPanel('impact')
  render(answer)
  const names = answer.value.variants.map((variant) => variant.name)
  expect(texts('#view table tr:first-child th')).toEqual(['Category', 'Base', ...names])
  const scores = panelImpactMonteCarlo.value.scores
  const rows = Array.from(document.querySelectorAll('#view table tr:not(:first-child)'))
  expect(rows).toHaveLength(scores.length)
  rows.forEach((row, i) => {
    expect(row.children).toHaveLength(2 + names.length)
    expect(row.children[1].textContent).toContain(fmt(scores[i].value))
  })
  names.forEach((_, column) => {
    rows.forEach((row, i) => {
      expect(row.children[2 + column].textContent).toContain(
        fmt(panelImpactMonteCarlo.value.variants[column].scores[i].value),
      )
    })
  })
})

it('draws the first part that a contribution answer lists, by process, by flow and by path', () => {
  const process = openPanel('contribution')
  process(byProcess)
  const processes = byProcess.value.processes ?? []
  expect(count('#view .row')).toBe(processes.length)
  expect(texts('#view .row .name')[0]).toBe(`${processes[0].name} [${processes[0].location}]`)

  const flow = openPanel('contribution')
  flow(byFlow)
  const flows = byFlow.value.flows ?? []
  expect(count('#view .row')).toBe(flows.length)
  expect(texts('#view .row .name')[0]).toBe(`${flows[0].name} (${flows[0].compartment})`)

  const tree = openPanel('contribution')
  tree(byPath)
  const root = byPath.value.root
  expect(root).not.toBeNull()
  expect(texts('#view li')[0]).toContain(root ? root.name : '')
})

it('draws a row for each row of an inventory answer', () => {
  const render = openPanel('inventory')
  render(inventory)
  expect(texts('#view tr:first-child th')).toEqual([
    'Flow',
    'Compartment',
    'Amount',
    'Unit',
    'Dominant process',
  ])
  expect(count('#view tr')).toBe(inventory.items.length + 1)
  const names = inventory.items.map((row) => row.name).sort()
  expect(texts('#view tr:not(:first-child) td:first-child')).toEqual(names)
  expect(texts('#title')).toEqual([`Inventory: ${inventory.items.length} rows`])
})

it('draws the link to the product system when the answer carries one view_url and none when it does not', () => {
  const answers: Record<string, object> = {
    impact: impact,
    contribution: byProcess,
    inventory: inventory,
  }
  for (const [panel, answer] of Object.entries(answers)) {
    const render = openPanel(panel)
    render({ ...answer, view_url: 'http://127.0.0.1:1/systems/abc/results' })
    expect(texts('#footer a')).toEqual(['Open the product system in the browser'])
    render({ ...answer, view_url: null })
    expect(count('#footer a')).toBe(0)
  }
})
