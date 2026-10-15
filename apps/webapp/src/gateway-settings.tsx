export function GatewaySettings(_props: { embedded?: boolean; subpage?: string } = {}) {
  return <section className="space-y-4 p-6 text-sm">
    <h2 className="font-medium">Browser gateway</h2>
    <p>This browser connects to {location.origin} using the authenticated Hermes web session.</p>
    <p>The service operator configures the backend. Native SSH tunnels, local installation, Cloud discovery, and token storage are unavailable here.</p>
    <a className="underline" href="/login?next=%2F">Sign in again</a>
  </section>
}
