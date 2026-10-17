const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(fetchImpl, initial = '') {
    function field(value = '') {
        return {value, handlers: {}, children: [], hidden: false,
            addEventListener(event, fn) {this.handlers[event] = fn;},
            dispatchEvent() {}, focus() {this.focused = true;},
            replaceChildren() {this.children = []; this.value = '';},
            appendChild(option) {this.children.push(option); if (this.children.length === 1) this.value = option.value;}};
    }
    const postal = field('０２９－４１０２');
    const address = field(initial);
    const search = field();
    const results = field(); results.hidden = true;
    const choices = field();
    const apply = field();
    const status = field();
    const map = {'[name="postal_code"]': postal, '[name="detail_address"]': address,
        '[data-postal-search]': search, '[data-postal-results]': results,
        '[data-postal-candidates]': choices, '[data-postal-apply]': apply, '#postal-status': status};
    const section = {dataset: {searchUrl: '/postal-addresses'}, querySelector(selector) {return map[selector];}};
    const confirmations = [];
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/postal-address.js'), 'utf8'), {
        document: {querySelectorAll() {return [section];}, createElement() {return field();}},
        fetch: fetchImpl, Event: class {}, window: {confirm(message) {confirmations.push(message); return false;}},
    });
    return {postal, address, search, results, choices, apply, status, confirmations};
}
const response = (addresses) => ({ok: true, async json() {return {addresses};}});

test('a single result fills empty address and sends only postal code', async () => {
    const requests = [];
    const ui = setup(async (url) => {requests.push(url); return response(['岩手県西磐井郡平泉町平泉']);});
    await ui.search.handlers.click();
    assert.equal(requests[0], '/postal-addresses?postal_code=0294102');
    assert.equal(ui.address.value, '岩手県西磐井郡平泉町平泉');
    assert.equal(ui.address.focused, true);
    assert.match(ui.status.textContent, /番地/);
    assert.equal(ui.search.disabled, false);
});

test('multiple candidates and existing address require deliberate selection', async () => {
    const ui = setup(async () => response(['町A', '町B']), '入力済み住所123-4');
    await ui.search.handlers.click();
    assert.equal(ui.address.value, '入力済み住所123-4');
    assert.equal(ui.results.hidden, false);
    assert.equal(ui.choices.children.length, 2);
    ui.apply.handlers.click();
    assert.equal(ui.confirmations.length, 1);
    assert.equal(ui.address.value, '入力済み住所123-4');
    ui.address.value = '';
    ui.choices.value = '町B';
    ui.apply.handlers.click();
    assert.equal(ui.address.value, '町B');
});

test('lookup failures, no result and invalid codes keep typed addresses', async () => {
    const ui = setup(async () => {throw new Error('offline');}, '手入力住所123-4');
    await ui.search.handlers.click();
    assert.equal(ui.address.value, '手入力住所123-4');
    assert.match(ui.status.textContent, /直接入力/);
    assert.equal(ui.search.disabled, false);
    const empty = setup(async () => response([]), '住所');
    await empty.search.handlers.click();
    assert.match(empty.status.textContent, /見つかりません/);
    assert.equal(empty.address.value, '住所');
    const invalid = setup(async () => {throw new Error('should not request');});
    invalid.postal.value = '123';
    await invalid.search.handlers.click();
    assert.match(invalid.status.textContent, /7桁/);
});

test('changing postal code discards a late lookup response', async () => {
    let resolve;
    const ui = setup(() => new Promise((done) => {resolve = done;}));
    const pending = ui.search.handlers.click();
    ui.postal.value = '1000001';
    ui.postal.handlers.input();
    resolve(response(['古い郵便番号の住所']));
    await pending;
    assert.equal(ui.address.value, '');
    assert.equal(ui.results.hidden, true);
    assert.equal(ui.search.disabled, false);
});
