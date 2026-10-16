const chatLogs = document.getElementById('chatLogs');
if (chatLogs) {
    chatLogs.scrollTop = chatLogs.scrollHeight;
}

// 3秒ごとのリアルタイム自動更新
let refreshInProgress = false;
const originalTitle = document.title;
if (chatLogs) {
setInterval(function () {
    if (refreshInProgress) return;
    refreshInProgress = true;
    fetch(window.location.href, { cache: 'no-store' })
        .then(response => {
            if (!response.ok || response.redirected) throw new Error('ページを取得できません');
            return response.text();
        })
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const status = document.getElementById('request-status');
            const nextStatus = doc.getElementById('request-status');
            const notification = document.getElementById('confirmation-notification');
            const completionNotification = document.getElementById('completion-notification');
            const newlyCompleted = status && nextStatus
                && status.dataset.state !== 'completed'
                && nextStatus.dataset.state === 'completed'
                && nextStatus.dataset.viewer === 'helper';
            if (status && nextStatus) {
                const newlyConfirmed = status.dataset.state === 'pending'
                    && nextStatus.dataset.state === 'confirmed'
                    && nextStatus.dataset.viewer === 'helper';
                if (status.outerHTML !== nextStatus.outerHTML) status.replaceWith(nextStatus);
                if (newlyConfirmed) {
                    notification.hidden = false;
                    document.title = '【依頼確定】' + originalTitle;
                }
            } else if (status) {
                status.remove();
            }
            if (!nextStatus || nextStatus.dataset.state !== 'confirmed') {
                notification.hidden = true;
                document.title = originalTitle;
            }
            if (newlyCompleted && completionNotification) {
                completionNotification.hidden = false;
                document.title = '【依頼終了】' + originalTitle;
            } else if (nextStatus && nextStatus.dataset.state === 'completed' && completionNotification && !completionNotification.hidden) {
                document.title = '【依頼終了】' + originalTitle;
            }
            const contact = document.getElementById('contact-details');
            const nextContact = doc.getElementById('contact-details');
            if (contact && nextContact && contact.innerHTML !== nextContact.innerHTML) {
                contact.replaceWith(nextContact);
            }
            const newChatLogs = doc.getElementById('chatLogs');
            if (newChatLogs && chatLogs) {
                if (chatLogs.innerHTML !== newChatLogs.innerHTML) {
                    chatLogs.innerHTML = newChatLogs.innerHTML;
                    chatLogs.scrollTop = chatLogs.scrollHeight;
                }
            }
        })
        .catch(err => console.log('更新待機中...'))
        .finally(() => { refreshInProgress = false; });
}, 3000);
}

document.addEventListener('click', function (event) {
    const link = event.target.closest('a[data-confirm]');
    if (link && !window.confirm(link.dataset.confirm)) {
        event.preventDefault();
    }
});

document.addEventListener('submit', function (event) {
    const form = event.target;
    if (form.matches('form[data-confirm]') && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
    }
});
