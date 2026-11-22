import type { ContributionResult, StagePart } from '@/api/types'
import { STAGE_TOKENS, stageByCode, stageColour, stageNames } from '@/lib/stageColours'
import { formatShare } from '@/lib/format'

function splitOf(stages: StagePart[]): ContributionResult {
  return { stages } as unknown as ContributionResult
}

function part(stage: string | null, code: string, score: number): StagePart {
  return {
    stage,
    score,
    fraction: score / 4.158,
    processes: [
      {
        ref: { kind: 'foreground', code },
        name: code,
        location: 'GLO',
        score,
        fraction: score / 4.158,
        direct: 0,
        inputs: [],
      },
    ],
  }
}

const SPLIT = splitOf([part('assembly', 'widget', 2.49), part('materials', 'frame', 1.668)])

it('the second of two stages takes the second colour token', () => {
  expect(stageColour(['a', 'b'], 'b')).toBe('rgb(var(--stage-2) / 1)')
})

it('a stage past the sixth token wraps back to the first', () => {
  const names = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
  expect(STAGE_TOKENS).toBe(6)
  expect(stageColour(names, 'g')).toBe('rgb(var(--stage-1) / 1)')
})

it('a part of no stage, or a name the split does not hold, takes the muted token', () => {
  expect(stageColour(['a', 'b'], null)).toBe('rgb(var(--muted-foreground) / 1)')
  expect(stageColour(['a', 'b'], 'c')).toBe('rgb(var(--muted-foreground) / 1)')
})

it('a colour carries the alpha it is asked for', () => {
  expect(stageColour(['a'], 'a', 0.6)).toBe('rgb(var(--stage-1) / 0.6)')
})

it('the names are the split’s stages in the order it gives them', () => {
  expect(stageNames(SPLIT)).toEqual(['assembly', 'materials'])
  expect(stageNames(splitOf([part(null, 'widget', 2.49)]))).toEqual([])
})

it('each own process takes the stage of the part that holds it', () => {
  expect([...stageByCode(SPLIT)]).toEqual([
    ['widget', 'assembly'],
    ['frame', 'materials'],
  ])
  expect([...stageByCode(splitOf([part(null, 'widget', 2.49)]))]).toEqual([['widget', null]])
})

it('a share is printed with the sign it carries', () => {
  expect(formatShare(-0.01 / 1.658)).toBe('-0.6 %')
})
