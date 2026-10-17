document.querySelectorAll('[data-postal-address]').forEach((section) => {
    const postal = section.querySelector('[name="postal_code"]');
    const address = section.querySelector('[name="detail_address"]');
    const search = section.querySelector('[data-postal-search]');
    const results = section.querySelector('[data-postal-results]');
    const choices = section.querySelector('[data-postal-candidates]');
    const apply = section.querySelector('[data-postal-apply]');
    const status = section.querySelector('#postal-status');
    let generation = 0;
    search.hidden = false;
    const normalizedCode = () => postal.value.normalize('NFKC').trim().replace(/-/g, '');
    postal.addEventListener('input', () => {
        generation += 1;
        results.hidden = true;
        status.textContent = '';
        search.disabled = false;
    });
    search.addEventListener('click', async () => {
        const code = normalizedCode();
        const request = ++generation;
        results.hidden = true;
        if (!/^[0-9]{7}$/.test(code)) {
            status.textContent = '郵便番号は7桁の数字で入力してください。';
            return;
        }
        search.disabled = true;
        status.textContent = '住所を検索しています…';
        try {
            const response = await fetch(`${section.dataset.searchUrl}?postal_code=${encodeURIComponent(code)}`, {
                credentials: 'same-origin', headers: {'Accept': 'application/json'},
            });
            if (!response.ok) throw new Error('lookup failed');
            const data = await response.json();
            if (request !== generation) return;
            const addresses = data.addresses;
            if (!Array.isArray(addresses) || !addresses.every((item) => typeof item === 'string')) throw new Error('invalid data');
            choices.replaceChildren();
            addresses.forEach((item) => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                choices.appendChild(option);
            });
            if (!addresses.length) {
                status.textContent = '住所が見つかりませんでした。郵便番号を確認するか、住所を直接入力してください。';
            } else if (addresses.length === 1 && !address.value.trim()) {
                address.value = addresses[0];
                address.dispatchEvent(new Event('input', {bubbles: true}));
                status.textContent = '町域まで入力しました。番地・建物名を追記してください。番地がない場所は目印・集合場所を記入してください。';
                address.focus();
            } else {
                results.hidden = false;
                status.textContent = '該当する住所を選び、住所欄に入力してください。入力済みの住所はまだ変更していません。';
            }
        } catch (error) {
            if (request === generation) status.textContent = '住所を検索できませんでした。もう一度試すか、住所を直接入力してください。';
        } finally {
            if (request === generation) search.disabled = false;
        }
    });
    apply.addEventListener('click', () => {
        if (results.hidden || !choices.value) return;
        if (address.value.trim() && address.value !== choices.value && !window.confirm('入力済みの住所を選択した住所に置き換えますか？ 番地・建物名は入力し直してください。')) return;
        address.value = choices.value;
        address.dispatchEvent(new Event('input', {bubbles: true}));
        status.textContent = '番地・建物名を追記してください。番地がない場所は目印・集合場所を記入してください。';
        address.focus();
    });
});
