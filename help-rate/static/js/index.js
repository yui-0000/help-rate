const postsList = document.getElementById('posts-list');
const postsUpdateStatus = document.getElementById('posts-update-status');
let postsRefreshInProgress = false;

async function refreshPosts() {
    if (document.hidden || postsRefreshInProgress) return;
    postsRefreshInProgress = true;
    try {
        const response = await fetch(postsList.dataset.refreshUrl, {cache: 'no-store'});
        if (!response.ok || response.redirected) throw new Error('更新できません');
        const html = await response.text();
        // Compare parsed HTML so browser normalization does not cause unnecessary updates.
        const incoming = document.createElement('div');
        incoming.innerHTML = html;
        if (postsList.innerHTML !== incoming.innerHTML) {
            const focused = postsList.contains(document.activeElement) ? document.activeElement : null;
            const focusedHref = focused && focused.getAttribute('href');
            postsList.innerHTML = incoming.innerHTML;
            if (focusedHref) {
                const replacement = Array.from(postsList.querySelectorAll('a'))
                    .find(link => link.getAttribute('href') === focusedHref);
                if (replacement) replacement.focus({preventScroll: true});
            }
            postsUpdateStatus.textContent = '新しい投稿・状態の変更を反映しました（3秒ごとに自動更新）';
        } else {
            postsUpdateStatus.textContent = '最新の募集一覧です（3秒ごとに自動更新）';
        }
    } catch (error) {
        postsUpdateStatus.textContent = '自動更新に接続できません。表示を残したまま再接続します。';
    } finally {
        postsRefreshInProgress = false;
    }
}

if (postsList) {
    setInterval(refreshPosts, 3000);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) refreshPosts();
    });
}
