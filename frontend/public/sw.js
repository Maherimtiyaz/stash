// Stash service worker: shows reminder notifications and opens the save when tapped.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Stash", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Stash reminder", {
      body: data.body || "",
      icon: "/app/icon-192.png",
      badge: "/app/icon-192.png",
      tag: data.tag || "stash",
      data: { url: data.url || "/app/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/app/", self.location.origin);
  if (url.origin !== self.location.origin) return; // only ever open Stash itself
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url.startsWith(self.location.origin + "/app")) return w.focus().then(() => w.navigate(url.href));
      }
      return self.clients.openWindow(url.href);
    }),
  );
});
