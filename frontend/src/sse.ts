/** Minimal SSE frame parser for a fetch() response body.
 *
 * EventSource can't do POST, so ai-plan.md's `POST /api/chat` stream is
 * consumed by hand: read raw bytes, split on the blank-line frame
 * delimiter, pull `event:`/`data:` lines out of each frame. One frame
 * always has exactly one JSON object per backend/harness.py's
 * format_sse(), so no multi-line `data:` accumulation is needed.
 */
export interface SSEFrame {
  event: string
  data: unknown
}

export async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let sep: number
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)

        let eventName = 'message'
        let dataLine: string | null = null
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) eventName = line.slice(7)
          else if (line.startsWith('data: ')) dataLine = line.slice(6)
        }
        if (dataLine !== null) {
          yield { event: eventName, data: JSON.parse(dataLine) }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
