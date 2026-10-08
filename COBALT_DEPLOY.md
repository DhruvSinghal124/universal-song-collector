# Deployment plan

Use TWO Render Web Services.

## Service 1: Cobalt API
Create a Render Docker Web Service from the `cobalt` folder.
Dockerfile: `cobalt/Dockerfile`.
Set `API_URL` to the final public URL of this Cobalt service and `API_PORT` to `10000`.

Cobalt's current docs recommend self-hosting for reliable API use and document `audioFormat=mp3` / `downloadMode=audio`.

## Service 2: Universal Song Collector
Deploy the root Dockerfile.
Set environment variable:
`COBALT_API_URL=https://YOUR-COBALT-SERVICE.onrender.com`

The student-facing URL is Service 2.
