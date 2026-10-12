# MediaMTX (stream server)

Receives the stream from OBS and re-serves it to viewers.

```bash
cd infra/mediamtx
docker compose up -d
docker compose logs -f mediamtx
```

| Direction | URL |
|---|---|
| OBS publishes to | `rtmp://localhost:1935/live` with stream key `table1` |
| Watch (HLS) | `http://localhost:8888/live/table1` |
| Watch (WebRTC) | `http://localhost:8889/live/table1` |
| Watch (RTSP / VLC) | `rtsp://localhost:8554/live/table1` |

## Test with no camera and no OBS

```bash
ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 \
  -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p \
  -f flv rtmp://localhost:1935/live/table1
```

Then open the HLS or WebRTC URL above in a browser.

Anyone on your network can publish to this server as written. Fine for a home
test; add authentication before exposing it.
