export interface ServerSentEvent {
  id: string | null
  event: string
  data: string
}

export function parseSseFrame(frame: string): ServerSentEvent | null {
  let id: string | null = null
  let event = 'message'
  const data: string[] = []

  for (const line of frame.split('\n')) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    let value = separator === -1 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'id') id = value
    else if (field === 'event') event = value || 'message'
    else if (field === 'data') data.push(value)
  }

  if (data.length === 0) return null
  return { id, event, data: data.join('\n') }
}

export async function consumeSseResponse(
  response: Response,
  onEvent: (event: ServerSentEvent) => void | Promise<void>,
): Promise<void> {
  if (!response.body) throw new Error('stream response body is unavailable')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const parsed = parseSseFrame(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (parsed) await onEvent(parsed)
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    const parsed = parseSseFrame(buffer)
    if (parsed) await onEvent(parsed)
  } finally {
    reader.releaseLock()
  }
}
