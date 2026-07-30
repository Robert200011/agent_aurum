export type AnswerLineKind = 'heading' | 'unordered' | 'ordered' | 'paragraph'
export type AnswerSegmentKind = 'text' | 'strong' | 'code' | 'citation'

export interface AnswerLine {
  kind: AnswerLineKind
  level: number
  prefix: string | null
  text: string
}

export interface AnswerSegment {
  kind: AnswerSegmentKind
  text: string
  citationId: number | null
}

const inlinePattern = /(\[(\d+)\]|`([^`\n]+)`|\*\*([^*\n]+)\*\*)/g

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
        citationId: null,
      })
    }

    if (match[2]) {
      segments.push({
        kind: 'citation',
        text: match[0],
        citationId: Number(match[2]),
      })
    } else if (match[3]) {
      segments.push({ kind: 'code', text: match[3], citationId: null })
    } else {
      segments.push({
        kind: 'strong',
        text: match[4] ?? match[0],
        citationId: null,
      })
    }
    cursor = index + match[0].length
  }

  if (cursor < text.length) {
    segments.push({
      kind: 'text',
      text: text.slice(cursor),
      citationId: null,
    })
  }
  return segments
}

export function citationLocation(citation: {
  page: number | null
  section: string | null
  sheet_name: string | null
  row_start: number | null
  row_end: number | null
}): string {
  const parts: string[] = []
  if (citation.page !== null) parts.push(`第 ${citation.page} 页`)
  if (citation.section) parts.push(citation.section)
  if (citation.sheet_name) parts.push(`工作表 ${citation.sheet_name}`)
  if (citation.row_start !== null) {
    const rows =
      citation.row_end !== null && citation.row_end !== citation.row_start
        ? `${citation.row_start}–${citation.row_end}`
        : String(citation.row_start)
    parts.push(`第 ${rows} 行`)
  }
  return parts.join(' · ') || '原文片段'
}
