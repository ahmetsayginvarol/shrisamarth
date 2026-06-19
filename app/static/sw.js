self.addEventListener('push', function (event) {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) {}

    const title = data.title || 'Shrisamarth';
    const options = {
        body: data.body || '',
        icon: '/static/img/icon-192.png',
        badge: '/static/img/icon-72.png',
        data: { url: data.url || '/admin' },
        requireInteraction: true,
        vibrate: [200, 100, 200, 100, 200],
        tag: 'shrisamarth-alert',
        renotify: true,
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) || '/admin';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
            for (const client of list) {
                if ('focus' in client) {
                    client.navigate(targetUrl);
                    return client.focus();
                }
            }
            if (clients.openWindow) return clients.openWindow(targetUrl);
        })
    );
});
