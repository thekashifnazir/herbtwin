# Read time, photo in to answer page (2026-10-17)

Local server (Mac, home broadband) on main at 2328d81, with the live switches from the private working repo's `deploy.sh` (GLM-5.3-Flash reads the photo with DeepSeek-V4.1-Flash as backup and a 90 s photo timeout; Nemotron 3 Super x3 advises; Nano chats; Tavily, search and spot on). Off locally, as they do not change the time: the Cloudflare edge guard and the visitor caps; LangSmith traces went to a separate project. Signed out; place typed: London; one read at a time.

- Reads 10 of 10: median **19.9 s**, range 17.66 to 31.98 s
- The backup photo model read 0 of 10 photos
- Recorded model cost $0.0431 (voice and chat not included)

| Photo | Read (s) | Answer page (s) | Total (s) | Photo read by | Model calls |
|---|---|---|---|---|---|
| 1-parsley-healthy.jpg | 17.69 | 0.05 | 17.74 | zai-org/GLM-5.3-Flash | 4 |
| 3-basil-yellow-leaves.jpg | 19.47 | 0.0 | 19.47 | zai-org/GLM-5.3-Flash | 5 |
| 4-rosemary-beetles.jpg | 31.97 | 0.0 | 31.98 | zai-org/GLM-5.3-Flash | 5 |
| 5-coriander-flowering.jpg | 17.65 | 0.0 | 17.66 | zai-org/GLM-5.3-Flash | 4 |
| 6-basil-downy-mildew.jpg | 20.22 | 0.0 | 20.22 | zai-org/GLM-5.3-Flash | 5 |
| 1-parsley-healthy.jpg | 20.91 | 0.0 | 20.91 | zai-org/GLM-5.3-Flash | 4 |
| 3-basil-yellow-leaves.jpg | 24.14 | 0.0 | 24.14 | zai-org/GLM-5.3-Flash | 4 |
| 4-rosemary-beetles.jpg | 19.63 | 0.0 | 19.63 | zai-org/GLM-5.3-Flash | 5 |
| 5-coriander-flowering.jpg | 18.02 | 0.0 | 18.03 | zai-org/GLM-5.3-Flash | 4 |
| 6-basil-downy-mildew.jpg | 26.09 | 0.0 | 26.09 | zai-org/GLM-5.3-Flash | 5 |

## Live spot check (measured by the integrating session, 17 Oct)

Live site, revision `herbtwin-00030-scf`, through Cloudflare and Cloud Run (London), with
the judges' code, place "London". `/api/analyse` end to end (curl `time_total`), n = 3:

| Photo | Total (s) |
|---|---|
| 1-parsley-healthy.jpg | 24.4 |
| 4-rosemary-beetles.jpg | 25.8 |
| 6-basil-downy-mildew.jpg | 23.9 |

24 to 26 s live, against a local median of 19.9 s above: the live path adds the edge, the
container and the network to Cloud Run. Not taken with `scripts/time_reads.py` (which
times the streamed page and the answer page); the API call returns the answer directly.
