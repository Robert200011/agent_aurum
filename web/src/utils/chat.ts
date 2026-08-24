export type AnswerLineKind = 'heading' | 'unordered' | 'ordered' | 'paragraph'
export type AnswerSegmentKind = 'text' | 'strong' | 'code'

export interface AnswerLine {
  kind: AnswerLineKind
  level: number
  prefix: string | null
  text: string
}

export interface AnswerSegment {
  kind: AnswerSegmentKind
  text: string
}

const inlinePattern = /(`([^`\n]+)`|\*\*([^*\n]+)\*\*)/g

export function parseAnswerLines(answer: string): AnswerLine[] {
  return answer
    .split(/\r?\n/)
    .map((rawLine): AnswerLine | null => {
      const line = rawLine.trim()
      if (!line) return null

      const heading = /^(#{1,3})\s+(.+)$/.exec(line)
      if (heading?.[1] && heading[2]) {
        return {
          kind: 'heading',
          level: heading[1].length,
          prefix: null,
          text: heading[2],
        }
      }

      const unordered = /^[-*]\s+(.+)$/.exec(line)
      if (unordered?.[1]) {
        return { kind: 'unordered', level: 0, prefix: '•', text: unordered[1] }
      }

      const ordered = /^(\d+)[.)]\s+(.+)$/.exec(line)
      if (ordered?.[1] && ordered[2]) {
        return {
          kind: 'ordered',
          level: 0,
          prefix: `${ordered[1]}.`,
          text: ordered[2],
        }
      }

      return { kind: 'paragraph', level: 0, prefix: null, text: line }
    })
    .filter((line): line is AnswerLine => line !== null)
}

export function parseAnswerSegments(text: string): AnswerSegment[] {
  const segments: AnswerSegment[] = []
  let cursor = 0

  for (const match of text.matchAll(inlinePattern)) {
    const index = match.index ?? 0
    if (index > cursor) {
      segments.push({
        kind: 'text',
        text: text.slice(cursor, index),
      })
    }

    if (match[2]) {
      segments.push({ kind: 'code', text: match[2] })
    } else {
      segments.push({
        kind: 'strong',
        text: match[3] ?? match[0],
      })
    }
    cursor = index + match[0].length
  }

  if (cursor < text.length) {
    segments.push({
      kind: 'text',
      text: text.slice(cursor),
    })
  }
  return segments
}
