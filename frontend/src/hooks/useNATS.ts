import { useEffect, useRef, useState, useCallback } from 'react'

export interface NATSMessage {
  type: string
  data: any
  timestamp: string
}

export interface UseNATSOptions {
  url?: string
  onMessage?: (msg: NATSMessage) => void
  autoConnect?: boolean
}

export function useNATS(options: UseNATSOptions = {}) {
  const {
    url = 'ws://127.0.0.1:8080/ws',
    onMessage,
    autoConnect = true,
  } = options

  const [messages, setMessages] = useState<NATSMessage[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const messagesRef = useRef<NATSMessage[]>([])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        setError(null)
        console.log('[NATS WS] Connected to', url)
      }

      ws.onmessage = (event) => {
        try {
          const msg: NATSMessage = JSON.parse(event.data)

          // Add to message buffer (keep last 500)
          messagesRef.current = [...messagesRef.current.slice(-499), msg]
          setMessages(messagesRef.current)

          // External callback
          onMessage?.(msg)
        } catch {
          // Non-JSON message, ignore
        }
      }

      ws.onclose = () => {
        setConnected(false)
        console.log('[NATS WS] Disconnected')

        // Auto-reconnect after 3 seconds
        if (autoConnect) {
          reconnectTimerRef.current = window.setTimeout(() => {
            connect()
          }, 3000)
        }
      }

      ws.onerror = (e) => {
        setError('WebSocket connection error')
        console.error('[NATS WS] Error:', e)
      }
    } catch (e) {
      setError(`Failed to connect: ${e}`)
    }
  }, [url, onMessage, autoConnect])

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
  }, [])

  const subscribe = useCallback((layers: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'subscribe_layers',
        layers,
      }))
    }
  }, [])

  const selectEntity = useCallback((entityId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'entity.select',
        entity_id: entityId,
      }))
    }
  }, [])

  const publish = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect()
    }
    return () => {
      disconnect()
    }
  }, [autoConnect, connect, disconnect])

  return {
    messages,
    connected,
    error,
    connect,
    disconnect,
    subscribe,
    selectEntity,
    publish,
  }
}