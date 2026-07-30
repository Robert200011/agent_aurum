import { describe, expect, it } from 'vitest'

import { consumeSseResponse, parseSseFrame } from '@/services/sse'

describe('SSE parsing', () => {
  it('parses named events and joins multiple data lines', () => {
    expect(
      parseSseFrame(
        'id: 7\nevent: delta\ndata: {"delta":"第一行"}\ndata: {"extra":true}',
      ),
    ).toEqual({
      id: '7',
      event: 'delta',
      data: '{"delta":"第一行"}\n{"extra":true}',
    })
  })

  it('consumes events split across arbitrary network chunks', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      'id: 1\r\nevent: sta',
      'rt\r\ndata: {"message_id":"m1"}\r\n\r\n',
      'id: 2\nevent: delta\ndata: {"delta":"预算"}\n\n',
    ]
    const response = new Response(
      new ReadableStream({
        start(controller) {
          for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
          controller.close()
        },
      }),
      { headers: { 'Content-Type': 'text/event-stream' } },
    )
    const events: string[] = []

    await consumeSseResponse(response, (event) => {
      events.push(`${event.event}:${event.data}`)
    })

    expect(events).toEqual([
      'start:{"message_id":"m1"}',
      'delta:{"delta":"预算"}',
    ])
  })
})
