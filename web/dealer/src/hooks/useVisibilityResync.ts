import { useEffect } from 'react'
import { connect } from '../api/socket'

// iPadOS suspends background tabs and drops their sockets. Reconnect as soon
// as the page is visible again; the server replies with a fresh snapshot.
export function useVisibilityResync(): void {
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') connect()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('online', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('online', onVisible)
    }
  }, [])
}
