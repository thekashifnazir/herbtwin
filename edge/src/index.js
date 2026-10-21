// herbtwin's front door (spec D63): forward everything to Cloud Run with the edge secret and
// the visitor's IP; pass the response straight back, unbuffered, redirects included.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const headers = new Headers(request.headers);
    headers.set("x-herbtwin-edge", env.EDGE_SECRET);
    headers.set("x-herbtwin-visitor-ip", request.headers.get("cf-connecting-ip") || "");
    return fetch(new URL(url.pathname + url.search, env.ORIGIN), {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
    });
  },
};
