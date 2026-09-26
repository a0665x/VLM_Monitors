# Accounts and saved moments

## First sign-in

Start the host, then run `./run.sh account-setup` on that host. Open `/setup`, paste the one-time setup code and choose your administrator email and password (12–128 characters). Private account data stays in `data/private`, outside Git.

Local sign-in works immediately. Google sign-in uses your own Google Cloud OAuth **Web application** credentials. Set these values in the host environment file, then restart the service:

```dotenv
AUTH_PUBLIC_URL=https://your-host.your-tailnet.ts.net
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
AUTH_ALLOWED_EMAILS=family@example.com,friend@example.com
```

Register `https://your-host.your-tailnet.ts.net/auth/google/callback` as the exact authorized redirect URI in Google Cloud. Sign in locally and choose **Link Google account** to link the administrator. Allowed Google users become members; they can watch shared cameras, publish their own camera and manage their own archive. Host/model controls require the administrator. Connect phones through the existing Tailscale HTTPS address.

Sessions expire after 24 hours and sign-out revokes the server session. Camera pages, API reads and media signaling require sign-in. An already negotiated WebRTC connection should be closed on the client when signing out.

## Saved moments

Each account can enable one camera in **Saved moments**. Archiving is opt-in and independent of continuous AI analysis. The CPU compares small luminance images once a second; meaningful changes are saved, while an unchanged scene keeps a sample about once a minute. Analysis events preserve recent context and subsequent frames. Packet size/bitrate is not used as a scene detector.

Choose a retained UTC day to export a 12 fps MP4 using the CPU. The video has a UTC timestamp at the bottom right. Downloadable JSON maps each video frame to its original capture time, camera and reason. This is timestamp overlay plus a JSON sidecar; it does not embed a binary KLV stream.

## Storage policy

| Setting | Default |
| --- | --- |
| `ARCHIVE_RETENTION_DAYS` | 7 days |
| `ARCHIVE_QUOTA_MB` | 1024 MiB per account |
| `ARCHIVE_TOTAL_MB` | 10240 MiB across accounts |
| `ARCHIVE_MIN_FREE_MB` | Keep at least 1024 MiB free |
| `ARCHIVE_DIR` | `data/archive` (can be an external disk or NAS mount) |

Age and capacity both apply: retention can be shorter when capacity is reached. Older frames are removed first. Half the account budget is reserved for frames; remaining space accommodates the latest exported video and its replacement during encoding. Only the latest completed export is retained. Exports are serialized, software encoded, size bounded and stopped on storage pressure. Pending export files are removed on failure or restart. Low free space pauses recording; the page displays the reason and recording resumes when space is available. These limits cover archive files, not other applications or system logs. Use a dedicated filesystem quota for a hard operating-system limit shared with external writers.

No archive is enabled by default, and exporting does not load an AI model onto the GPU.
