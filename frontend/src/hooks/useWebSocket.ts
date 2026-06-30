import { useEffect, useRef, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'
import type { WSEvent } from '@/types/websocket'

type Handler = (event: WSEvent) => void

export function useWebSocket(onEvent: Handler) {
  const socketRef = useRef<Socket | null>(null)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    const socket = io('/', { transports: ['websocket'], autoConnect: true })
    socketRef.current = socket

    socket.onAny((eventName: string, data: unknown) => {
      handlerRef.current({ type: eventName, ...(data as object) } as WSEvent)
    })

    return () => { socket.disconnect() }
  }, [])

  const emit = useCallback((event: string, data?: unknown) => {
    socketRef.current?.emit(event, data)
  }, [])

  return { emit }
}